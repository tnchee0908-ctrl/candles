import { Plus, X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '@/api'
import { Page } from '@/components/layout/AppShell'
import {
  Banner,
  Button,
  Card,
  CardBody,
  CardFooter,
  Field,
  IconButton,
  Input,
  PageHeader,
  Select,
} from '@/components/ui'
import { businessDate } from '@/lib/format'
import type { Currency } from '@/lib/format'
import type { Material, ReceiptResult } from '@/types'

interface Line {
  id: number
  material_code: string
  qty: string
  price: string
  currency: Currency
  comment: string
}

const today = () => businessDate()
const plural = (n: number, one: string, few: string, many: string) => {
  const m10 = n % 10
  const m100 = n % 100
  if (m10 === 1 && m100 !== 11) return one
  if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return few
  return many
}

/** 07 — Поступление: поставщик с подсказками, строки, после успеха — баннер со ссылками на партии. */
export default function NewReceiptPage() {
  const navigate = useNavigate()
  const nextId = useRef(2)
  const [materials, setMaterials] = useState<Material[]>([])
  const [suppliers, setSuppliers] = useState<string[]>([])
  const [supplier, setSupplier] = useState('')
  const [date, setDate] = useState(today())
  const [lines, setLines] = useState<Line[]>([])
  const [errors, setErrors] = useState<Record<number, string>>({})
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<ReceiptResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [suggestOpen, setSuggestOpen] = useState(false)

  const emptyLine = (id: number, code = materials[0]?.code ?? ''): Line => ({
    id,
    material_code: code,
    qty: '',
    price: '',
    currency: 'RUB',
    comment: '',
  })

  useEffect(() => {
    api<Material[]>('/api/materials')
      .then((m) => {
        setMaterials(m)
        setLines([{ id: 1, material_code: m[0]?.code ?? '', qty: '', price: '', currency: 'RUB', comment: '' }])
      })
      .catch((e) => setError(e.message))
    api<string[]>('/api/suppliers')
      .then(setSuppliers)
      .catch(() => undefined)
  }, [])

  const suggestions = suppliers.filter(
    (s) => supplier && s.toLowerCase().includes(supplier.toLowerCase()) && s !== supplier,
  )
  const unitOf = (code: string) => materials.find((m) => m.code === code)?.unit ?? ''
  const update = (id: number, patch: Partial<Line>) =>
    setLines((ls) => ls.map((l) => (l.id === id ? { ...l, ...patch } : l)))
  const num = (v: string) => v.replace(/\s/g, '').replace(',', '.')

  async function submit() {
    const errs: Record<number, string> = {}
    lines.forEach((l) => {
      if (!(Number(num(l.qty)) > 0)) errs[l.id] = 'Укажите количество'
      else if (l.price === '' || Number(num(l.price)) < 0) errs[l.id] = 'Укажите цену'
    })
    setErrors(errs)
    if (Object.keys(errs).length) return
    setLoading(true)
    setError(null)
    try {
      const res = await api<ReceiptResult>('/api/receipts', {
        method: 'POST',
        json: {
          supplier,
          received_date: date,
          lines: lines.map((l) => ({
            material_code: l.material_code,
            qty: num(l.qty),
            price: num(l.price),
            currency: l.currency,
            comment: l.comment || null,
          })),
        },
      })
      setResult(res)
      setSupplier('')
      setLines([emptyLine(nextId.current++)])
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setLoading(false)
    }
  }

  const grid =
    'grid grid-cols-[minmax(200px,2.2fr)_minmax(110px,1fr)_minmax(110px,1fr)_92px_minmax(140px,1.6fr)_32px] items-center gap-2'

  return (
    <Page>
      <PageHeader
        title="Поступление от поставщика"
        subtitle="Каждая строка станет партией «На проверке». Себестоимость считается в рублях по курсу на дату поступления."
      />
      <div className="flex flex-col gap-4">
        {error && <Banner tone="error">{error}</Banner>}
        {result && (
          <Banner tone="success" title={`Поступление ${result.number} оформлено.`} onDismiss={() => setResult(null)}>
            Созданы партии{' '}
            {result.batches.map((b, i) => (
              <span key={b.id}>
                {i > 0 && ', '}
                <Link to={`/batches/${b.id}`} className="text-accent hover:underline">
                  {b.number}
                </Link>
              </span>
            ))}{' '}
            — статус «На проверке».
          </Banner>
        )}

        <Card>
          <CardBody className="grid grid-cols-[minmax(0,2fr)_minmax(0,1fr)] gap-4 pb-5">
            <Field label="Поставщик" htmlFor="supplier" required className="relative">
              <Input
                id="supplier"
                autoComplete="off"
                value={supplier}
                onChange={(e) => {
                  setSupplier(e.target.value)
                  setSuggestOpen(true)
                }}
                onBlur={() => setTimeout(() => setSuggestOpen(false), 120)}
                aria-expanded={suggestOpen && suggestions.length > 0}
                aria-autocomplete="list"
              />
              {suggestOpen && suggestions.length > 0 && (
                <ul
                  role="listbox"
                  className="absolute left-0 right-0 top-[64px] z-20 rounded-lg border border-border bg-surface p-1 shadow-popover"
                >
                  {suggestions.map((s) => (
                    <li key={s} role="option" aria-selected={false}>
                      <button
                        type="button"
                        className="flex h-8 w-full items-center rounded px-2 text-left hover:bg-muted"
                        onMouseDown={() => setSupplier(s)}
                      >
                        {s}
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </Field>
            <Field label="Дата поступления" htmlFor="date" required>
              <Input id="date" type="date" max={today()} value={date} onChange={(e) => setDate(e.target.value)} />
            </Field>
          </CardBody>
          <hr className="border-border-soft" />
          <CardBody>
            <div className={`${grid} mb-1.5 text-sm font-medium text-fg-label`}>
              <span>Материал</span>
              <span className="text-right">Количество</span>
              <span className="text-right">Цена за ед.</span>
              <span>Валюта</span>
              <span>Комментарий</span>
              <span />
            </div>
            <div className="flex flex-col gap-2">
              {lines.map((l, i) => (
                <div key={l.id}>
                  <div className={grid}>
                    <Select
                      aria-label={`Материал, строка ${i + 1}`}
                      value={l.material_code}
                      onChange={(e) => update(l.id, { material_code: e.target.value })}
                    >
                      {materials.map((m) => (
                        <option key={m.code} value={m.code}>
                          {m.name} · {m.code}
                        </option>
                      ))}
                    </Select>
                    <Input
                      numeric
                      suffix={unitOf(l.material_code)}
                      aria-label={`Количество, строка ${i + 1}`}
                      invalid={Boolean(errors[l.id]) && !(Number(num(l.qty)) > 0)}
                      value={l.qty}
                      onChange={(e) => update(l.id, { qty: e.target.value })}
                    />
                    <Input
                      numeric
                      aria-label={`Цена, строка ${i + 1}`}
                      invalid={errors[l.id] === 'Укажите цену'}
                      value={l.price}
                      onChange={(e) => update(l.id, { price: e.target.value })}
                    />
                    <Select
                      aria-label={`Валюта, строка ${i + 1}`}
                      value={l.currency}
                      onChange={(e) => update(l.id, { currency: e.target.value as Currency })}
                    >
                      <option>RUB</option>
                      <option>USD</option>
                      <option>EUR</option>
                    </Select>
                    <Input
                      placeholder="Необязательно"
                      aria-label={`Комментарий, строка ${i + 1}`}
                      value={l.comment}
                      onChange={(e) => update(l.id, { comment: e.target.value })}
                    />
                    <IconButton
                      label={`Удалить строку ${i + 1}`}
                      tone="danger"
                      disabled={lines.length === 1}
                      onClick={() => setLines((ls) => ls.filter((x) => x.id !== l.id))}
                    >
                      <X />
                    </IconButton>
                  </div>
                  {errors[l.id] && (
                    <div className={`${grid} mt-1`}>
                      <span />
                      <span className="text-right text-xs text-danger-fg">{errors[l.id]}</span>
                    </div>
                  )}
                </div>
              ))}
            </div>
            <Button
              variant="ghost"
              size="sm"
              icon={<Plus />}
              className="-ml-1.5 mt-2.5"
              onClick={() => setLines((ls) => [...ls, emptyLine(nextId.current++)])}
            >
              Добавить строку
            </Button>
          </CardBody>
          <CardFooter>
            <span className="text-sm text-fg-muted">
              {lines.length} {plural(lines.length, 'строка', 'строки', 'строк')} → {lines.length}{' '}
              {plural(lines.length, 'партия', 'партии', 'партий')} «На проверке»
            </span>
            <div className="flex gap-2">
              <Button variant="ghost" onClick={() => navigate('/batches')}>
                Отмена
              </Button>
              <Button
                variant="primary"
                loading={loading}
                disabledReason={!supplier.trim() ? 'Укажите поставщика' : undefined}
                onClick={submit}
              >
                Оформить поступление
              </Button>
            </div>
          </CardFooter>
        </Card>
      </div>
    </Page>
  )
}
