import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import PreviewTable from '../components/PreviewTable'
import { Button, Card, ErrorBox, Field, PageHeader, inputCls } from '../components/ui'
import { todayIso } from '../format'
import type { OrderCard, PreviewRow, Recipe } from '../types'

export default function NewOrderPage() {
  const navigate = useNavigate()
  const [recipes, setRecipes] = useState<Recipe[]>([])
  const [recipeId, setRecipeId] = useState<number | ''>('')
  const [qty, setQty] = useState('100')
  const [date, setDate] = useState(todayIso(1))
  const [workshop, setWorkshop] = useState('1')
  const [comment, setComment] = useState('')
  const [preview, setPreview] = useState<PreviewRow[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    api<Recipe[]>('/api/recipes')
      .then((r) => {
        setRecipes(r)
        if (r.length) setRecipeId(r[0].id)
      })
      .catch((e) => setError(e.message))
  }, [])

  useEffect(() => {
    const n = Number(qty)
    if (!recipeId || !Number.isInteger(n) || n <= 0) {
      setPreview(null)
      return
    }
    const t = setTimeout(() => {
      api<PreviewRow[]>(`/api/orders/preview?recipe_id=${recipeId}&qty=${n}`)
        .then(setPreview)
        .catch(() => setPreview(null))
    }, 300)
    return () => clearTimeout(t)
  }, [recipeId, qty])

  async function submit(planNow: boolean) {
    setBusy(true)
    setError(null)
    try {
      const card = await api<OrderCard>('/api/orders', {
        method: 'POST',
        json: { recipe_id: recipeId, qty: Number(qty), planned_date: date, workshop: Number(workshop), comment: comment || null, plan_now: planNow },
      })
      navigate(`/orders/${card.id}`)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="max-w-3xl">
      <PageHeader title="Новое задание" subtitle="При планировании материалы резервируются по FIFO — из самых старых принятых партий." />
      <ErrorBox error={error} />
      <Card>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Продукт (рецепт)">
            <select className={inputCls} value={recipeId} onChange={(e) => setRecipeId(Number(e.target.value))}>
              {recipes.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Количество, шт">
            <input className={inputCls} type="number" min={1} value={qty} onChange={(e) => setQty(e.target.value)} />
          </Field>
          <Field label="Плановая дата">
            <input className={inputCls} type="date" min={todayIso()} value={date} onChange={(e) => setDate(e.target.value)} />
          </Field>
          <Field label="Цех">
            <select className={inputCls} value={workshop} onChange={(e) => setWorkshop(e.target.value)}>
              <option value="1">1</option>
              <option value="2">2</option>
              <option value="3">3</option>
            </select>
          </Field>
          <div className="sm:col-span-2">
            <Field label="Комментарий">
              <input className={inputCls} value={comment} onChange={(e) => setComment(e.target.value)} />
            </Field>
          </div>
        </div>
      </Card>
      {preview && (
        <div className="mt-4">
          <Card title="Что будет зарезервировано сейчас">
            <PreviewTable rows={preview} />
            {preview.some((r) => Number(r.shortage) > 0) && (
              <p className="mt-2 text-sm text-amber-700">
                Есть дефицит: задание будет запланировано с частичным резервом, запустить его можно будет после
                дорезервирования.
              </p>
            )}
          </Card>
        </div>
      )}
      <div className="mt-4 flex gap-2">
        <Button disabled={busy || !recipeId} onClick={() => submit(true)}>
          Создать и запланировать
        </Button>
        <Button variant="secondary" disabled={busy || !recipeId} onClick={() => submit(false)}>
          Сохранить черновик
        </Button>
      </div>
    </div>
  )
}
