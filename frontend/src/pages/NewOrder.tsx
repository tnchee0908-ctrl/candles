import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { api } from '@/api'
import { Page } from '@/components/layout/AppShell'
import {
  Banner,
  Button,
  Card,
  CardBody,
  CardFooter,
  CardHeader,
  Dash,
  Field,
  Input,
  MaterialCode,
  PageHeader,
  Qty,
  ReserveDot,
  ReserveLegend,
  Select,
  Table,
  TableScroll,
  TableSkeleton,
  Td,
  Textarea,
  Th,
  Tr,
} from '@/components/ui'
import { businessDate, formatQty } from '@/lib/format'
import { levelByQty } from '@/lib/reserve'
import type { OrderCard, PreviewRow, Recipe } from '@/types'

const isoDate = businessDate

/** 13 — Новое задание: форма + живой предпросмотр «что будет зарезервировано». */
export default function NewOrderPage() {
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const [recipes, setRecipes] = useState<Recipe[]>([])
  const [recipeId, setRecipeId] = useState<number | ''>('')
  const [qty, setQty] = useState('100')
  const [date, setDate] = useState(isoDate(1))
  const [workshop, setWorkshop] = useState('1')
  const [comment, setComment] = useState('')
  const [preview, setPreview] = useState<PreviewRow[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState<'plan' | 'draft' | null>(null)

  useEffect(() => {
    api<Recipe[]>('/api/recipes')
      .then((r) => {
        setRecipes(r)
        const fromLink = Number(params.get('recipe'))
        setRecipeId(r.find((x) => x.id === fromLink)?.id ?? r[0]?.id ?? '')
      })
      .catch((e) => setError(e.message))
  }, [params])

  const n = Number(qty)
  const qtyValid = Number.isInteger(n) && n > 0 && n <= 100_000

  useEffect(() => {
    if (!recipeId || !qtyValid) {
      setPreview(null)
      return
    }
    const t = setTimeout(() => {
      api<PreviewRow[]>(`/api/orders/preview?recipe_id=${recipeId}&qty=${n}`)
        .then(setPreview)
        .catch(() => setPreview(null))
    }, 300)
    return () => clearTimeout(t)
  }, [recipeId, n, qtyValid])

  async function submit(planNow: boolean) {
    setBusy(planNow ? 'plan' : 'draft')
    setError(null)
    try {
      const card = await api<OrderCard>('/api/orders', {
        method: 'POST',
        json: {
          recipe_id: recipeId,
          qty: n,
          planned_date: date,
          workshop: Number(workshop),
          comment: comment.trim() || null,
          plan_now: planNow,
        },
      })
      navigate(`/orders/${card.id}`)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(null)
    }
  }

  const hasDeficit = preview?.some((p) => Number(p.shortage) > 0)
  const blocked = !recipeId ? 'Выберите рецепт' : !qtyValid ? 'Укажите количество от 1 до 100 000' : undefined

  return (
    <Page>
      <PageHeader
        breadcrumbs={[{ label: 'Задания', to: '/orders' }, { label: 'Новое' }]}
        title="Новое задание"
        subtitle="При планировании материалы резервируются по FIFO — из самых старых принятых партий."
      />
      {error && <Banner tone="error" className="mb-4">{error}</Banner>}
      <div className="flex flex-wrap items-start gap-4">
        <Card className="max-w-[400px] flex-[1_1_340px]">
          <CardHeader title="Параметры" />
          <CardBody className="flex flex-col gap-3.5">
            <Field label="Продукт (рецепт)" htmlFor="recipe" required>
              <Select id="recipe" value={recipeId} onChange={(e) => setRecipeId(Number(e.target.value))}>
                {recipes.map((r) => (
                  <option key={r.id} value={r.id}>
                    Свеча «{r.name}»
                  </option>
                ))}
              </Select>
            </Field>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Количество" htmlFor="qty" required error={qty && !qtyValid ? 'Целое число до 100 000' : undefined}>
                <Input id="qty" numeric suffix="шт" invalid={Boolean(qty) && !qtyValid} value={qty} onChange={(e) => setQty(e.target.value)} />
              </Field>
              <Field label="Цех" htmlFor="ws" required>
                <Select id="ws" value={workshop} onChange={(e) => setWorkshop(e.target.value)}>
                  <option>1</option>
                  <option>2</option>
                  <option>3</option>
                </Select>
              </Field>
            </div>
            <Field label="Плановая дата" htmlFor="pd" required>
              <Input id="pd" type="date" min={isoDate()} value={date} onChange={(e) => setDate(e.target.value)} />
            </Field>
            <Field label="Комментарий" htmlFor="cm">
              <Textarea
                id="cm"
                placeholder="Например: под заказ магазина"
                value={comment}
                onChange={(e) => setComment(e.target.value)}
              />
            </Field>
          </CardBody>
          <CardFooter className="flex-col items-stretch gap-2">
            <Button
              variant="primary"
              fullWidth
              loading={busy === 'plan'}
              disabled={busy !== null}
              disabledReason={blocked}
              onClick={() => submit(true)}
            >
              Создать и запланировать
            </Button>
            <Button fullWidth loading={busy === 'draft'} disabled={busy !== null || Boolean(blocked)} onClick={() => submit(false)}>
              Сохранить черновик
            </Button>
          </CardFooter>
        </Card>

        <Card className="min-w-0 flex-[999_1_480px]">
          <CardHeader
            title="Что будет зарезервировано сейчас"
            description="Пересчитывается при изменении рецепта и количества"
            actions={<ReserveLegend />}
          />
          {!preview ? (
            qtyValid ? (
              <TableSkeleton rows={5} cols={4} />
            ) : (
              <div className="px-5 py-6 text-sm text-fg-muted">Укажите количество, чтобы увидеть резерв.</div>
            )
          ) : (
            <TableScroll>
              <Table minWidth={520} aria-live="polite">
                <thead>
                  <tr>
                    <Th className="w-11">
                      <span className="sr-only">Резерв</span>
                    </Th>
                    <Th>Материал</Th>
                    <Th align="right">Нужно</Th>
                    <Th align="right">Свободно</Th>
                    <Th align="right">Дефицит</Th>
                  </tr>
                </thead>
                <tbody>
                  {preview.map((p) => {
                    const shortage = Number(p.shortage)
                    return (
                      <Tr key={p.material_code} highlight={shortage > 0}>
                        <Td>
                          <ReserveDot level={levelByQty(Number(p.required), Number(p.free_now))} />
                        </Td>
                        <Td>
                          {p.material}
                          <MaterialCode>{p.material_code}</MaterialCode>
                        </Td>
                        <Td align="right">
                          <Qty value={formatQty(p.required)} unit={p.unit} />
                        </Td>
                        <Td align="right" className={Number(p.free_now) <= 0 ? 'text-danger-fg' : undefined}>
                          {formatQty(p.free_now)}
                        </Td>
                        <Td align="right">
                          {shortage > 0 ? (
                            <span className="font-semibold text-danger-fg">
                              {formatQty(shortage)} <span className="font-normal">{p.unit}</span>
                            </span>
                          ) : (
                            <Dash />
                          )}
                        </Td>
                      </Tr>
                    )
                  })}
                </tbody>
              </Table>
            </TableScroll>
          )}
          {hasDeficit && (
            <div className="px-4 pb-4 pt-3">
              <Banner tone="warning" title="Есть дефицит.">
                Задание будет запланировано с частичным резервом, запустить его можно будет после дорезервирования.
              </Banner>
            </div>
          )}
        </Card>
      </div>
    </Page>
  )
}
