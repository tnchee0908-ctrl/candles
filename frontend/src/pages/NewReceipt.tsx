import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { Button, Card, ErrorBox, Field, Notice, PageHeader, inputCls } from '../components/ui'
import { todayIso } from '../format'
import type { Material } from '../types'

interface Line {
  material_code: string
  qty: string
  price: string
  currency: 'RUB' | 'USD' | 'EUR'
  comment: string
}

const emptyLine = (code = ''): Line => ({ material_code: code, qty: '', price: '', currency: 'RUB', comment: '' })

export default function NewReceiptPage() {
  const [materials, setMaterials] = useState<Material[]>([])
  const [suppliers, setSuppliers] = useState<string[]>([])
  const [supplier, setSupplier] = useState('')
  const [date, setDate] = useState(todayIso())
  const [lines, setLines] = useState<Line[]>([emptyLine()])
  const [error, setError] = useState<string | null>(null)
  const [created, setCreated] = useState<{ number: string; batch_numbers: string[] } | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    api<Material[]>('/api/materials')
      .then((m) => {
        setMaterials(m)
        setLines([emptyLine(m[0]?.code ?? '')])
      })
      .catch((e) => setError(e.message))
    api<string[]>('/api/suppliers').then(setSuppliers).catch(() => undefined)
  }, [])

  const update = (i: number, patch: Partial<Line>) => setLines(lines.map((l, j) => (j === i ? { ...l, ...patch } : l)))

  async function submit() {
    setBusy(true)
    setError(null)
    try {
      const res = await api<{ number: string; batch_numbers: string[] }>('/api/receipts', {
        method: 'POST',
        json: {
          supplier,
          received_date: date,
          lines: lines.map((l) => ({
            material_code: l.material_code,
            qty: l.qty.replace(',', '.'),
            price: l.price.replace(',', '.'),
            currency: l.currency,
            comment: l.comment || null,
          })),
        },
      })
      setCreated(res)
      setLines([emptyLine(materials[0]?.code ?? '')])
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="max-w-5xl">
      <PageHeader
        title="Поступление от поставщика"
        subtitle="Каждая строка станет партией «На проверке». Себестоимость считается в рублях по курсу на дату поступления."
      />
      <ErrorBox error={error} />
      {created && (
        <Notice>
          Поступление {created.number} оформлено, партии: {created.batch_numbers.join(', ')}.{' '}
          <Link className="underline" to="/batches?status=on_check">
            Перейти к приёмке
          </Link>
        </Notice>
      )}
      <Card>
        <div className="mb-4 grid gap-3 sm:grid-cols-2">
          <Field label="Поставщик">
            <input className={inputCls} list="suppliers" value={supplier} onChange={(e) => setSupplier(e.target.value)} />
            <datalist id="suppliers">
              {suppliers.map((s) => (
                <option key={s} value={s} />
              ))}
            </datalist>
          </Field>
          <Field label="Дата поступления">
            <input className={inputCls} type="date" max={todayIso()} value={date} onChange={(e) => setDate(e.target.value)} />
          </Field>
        </div>
        <div className="space-y-2">
          {lines.map((l, i) => (
            <div key={i} className="grid grid-cols-12 items-end gap-2">
              <div className="col-span-4">
                <Field label={i === 0 ? 'Материал' : ''}>
                  <select className={inputCls} value={l.material_code} onChange={(e) => update(i, { material_code: e.target.value })}>
                    {materials.map((m) => (
                      <option key={m.code} value={m.code}>
                        {m.name} ({m.unit})
                      </option>
                    ))}
                  </select>
                </Field>
              </div>
              <div className="col-span-2">
                <Field label={i === 0 ? 'Количество' : ''}>
                  <input className={inputCls} inputMode="decimal" value={l.qty} onChange={(e) => update(i, { qty: e.target.value })} />
                </Field>
              </div>
              <div className="col-span-2">
                <Field label={i === 0 ? 'Цена за ед.' : ''}>
                  <input className={inputCls} inputMode="decimal" value={l.price} onChange={(e) => update(i, { price: e.target.value })} />
                </Field>
              </div>
              <div className="col-span-1">
                <Field label={i === 0 ? 'Валюта' : ''}>
                  <select className={inputCls} value={l.currency} onChange={(e) => update(i, { currency: e.target.value as Line['currency'] })}>
                    <option>RUB</option>
                    <option>USD</option>
                    <option>EUR</option>
                  </select>
                </Field>
              </div>
              <div className="col-span-2">
                <Field label={i === 0 ? 'Комментарий' : ''}>
                  <input className={inputCls} value={l.comment} onChange={(e) => update(i, { comment: e.target.value })} />
                </Field>
              </div>
              <div className="col-span-1">
                <Button variant="ghost" disabled={lines.length === 1} onClick={() => setLines(lines.filter((_, j) => j !== i))}>
                  ✕
                </Button>
              </div>
            </div>
          ))}
        </div>
        <div className="mt-4 flex gap-2">
          <Button variant="secondary" onClick={() => setLines([...lines, emptyLine(materials[0]?.code ?? '')])}>
            + Строка
          </Button>
          <Button disabled={busy || !supplier} onClick={submit}>
            Оформить поступление
          </Button>
        </div>
      </Card>
    </div>
  )
}
