import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api } from '../api'
import { useAuth } from '../auth'
import { Button, ErrorBox, PageHeader, StatusBadge, inputCls, td, tdNum, th } from '../components/ui'
import { day, money, num } from '../format'
import type { BatchRow, Page } from '../types'

type Col = {
  key: string
  label: string
  numeric?: boolean
  filter?: 'text' | 'status' | 'currency' | 'date'
}

const COLUMNS: Col[] = [
  { key: 'number', label: 'Номер', filter: 'text' },
  { key: 'received_date', label: 'Дата', filter: 'date' },
  { key: 'material', label: 'Материал', filter: 'text' },
  { key: 'supplier', label: 'Поставщик', filter: 'text' },
  { key: 'qty', label: 'Пришло', numeric: true },
  { key: 'remaining_qty', label: 'Остаток', numeric: true },
  { key: 'reserved_qty', label: 'Резерв', numeric: true },
  { key: 'free_qty', label: 'Свободно', numeric: true },
  { key: 'price', label: 'Цена', numeric: true },
  { key: 'currency', label: 'Валюта', filter: 'currency' },
  { key: 'unit_cost_rub', label: 'Себест., ₽/ед', numeric: true },
  { key: 'status', label: 'Статус', filter: 'status' },
]

const FILTER_KEYS = ['number', 'material', 'supplier', 'status', 'currency', 'date_from', 'date_to']

/** Фильтры, сортировка и страница живут в URL — ссылкой на реестр можно поделиться. */
export default function BatchesPage() {
  const { can } = useAuth()
  const [params, setParams] = useSearchParams()
  const [data, setData] = useState<Page<BatchRow> | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [drafts, setDrafts] = useState<Record<string, string>>(() =>
    Object.fromEntries(FILTER_KEYS.map((k) => [k, params.get(k) ?? ''])),
  )

  const sort = params.get('sort') ?? 'received_date'
  const direction = params.get('direction') ?? 'desc'
  const page = Number(params.get('page') ?? 1)
  const pageSize = Number(params.get('page_size') ?? 20)
  const query = params.toString()

  useEffect(() => {
    const q = new URLSearchParams(query)
    if (!q.get('sort')) q.set('sort', 'received_date')
    api<Page<BatchRow>>(`/api/batches?${q.toString()}`)
      .then((d) => {
        setData(d)
        setError(null)
      })
      .catch((e) => setError(e.message))
  }, [query])

  // Текстовые фильтры применяем с небольшой задержкой, чтобы не дёргать сервер на каждую букву.
  useEffect(() => {
    const t = setTimeout(() => {
      const next = new URLSearchParams(params)
      let changed = false
      for (const k of FILTER_KEYS) {
        const v = drafts[k]?.trim() ?? ''
        if ((params.get(k) ?? '') !== v) {
          changed = true
          if (v) next.set(k, v)
          else next.delete(k)
        }
      }
      if (changed) {
        next.set('page', '1')
        setParams(next, { replace: true })
      }
    }, 350)
    return () => clearTimeout(t)
  }, [drafts, params, setParams])

  function setParam(key: string, value: string | null) {
    const next = new URLSearchParams(params)
    if (value === null || value === '') next.delete(key)
    else next.set(key, value)
    setParams(next)
  }

  function toggleSort(key: string) {
    const next = new URLSearchParams(params)
    if (sort === key) next.set('direction', direction === 'asc' ? 'desc' : 'asc')
    else {
      next.set('sort', key)
      next.set('direction', 'asc')
    }
    next.set('page', '1')
    setParams(next)
  }

  const totalPages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1
  const hasFilters = FILTER_KEYS.some((k) => params.get(k))

  return (
    <div>
      <PageHeader
        title="Реестр партий"
        subtitle="Фильтр — строка под заголовками, сортировка — клик по заголовку."
        actions={
          <>
            {hasFilters && (
              <Button
                variant="ghost"
                onClick={() => {
                  setDrafts(Object.fromEntries(FILTER_KEYS.map((k) => [k, ''])))
                  setParams({})
                }}
              >
                Сбросить фильтры
              </Button>
            )}
            {can('create_receipt') && (
              <Link to="/receipts/new">
                <Button>+ Поступление</Button>
              </Link>
            )}
          </>
        }
      />
      <ErrorBox error={error} />
      <div className="overflow-x-auto rounded-lg border border-stone-200 bg-white shadow-sm">
        <table className="min-w-full text-sm">
          <thead>
            <tr>
              {COLUMNS.map((c) => (
                <th
                  key={c.key}
                  className={`${th} cursor-pointer select-none hover:text-stone-800 ${c.numeric ? 'text-right' : ''}`}
                  onClick={() => toggleSort(c.key)}
                >
                  {c.label}
                  <span className="ml-1 inline-block w-2">{sort === c.key ? (direction === 'asc' ? '▲' : '▼') : ''}</span>
                </th>
              ))}
            </tr>
            <tr className="bg-stone-50">
              {COLUMNS.map((c) => (
                <th key={c.key} className="border-b border-stone-200 px-2 py-1.5 font-normal">
                  <ColumnFilter col={c} drafts={drafts} setDrafts={setDrafts} />
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data?.items.map((b) => (
              <tr key={b.id} className="hover:bg-wax-50">
                <td className={td}>
                  <Link to={`/batches/${b.id}`} className="font-medium text-wax-700 hover:underline">
                    {b.number}
                  </Link>
                </td>
                <td className={td}>{day(b.received_date)}</td>
                <td className={td}>
                  {b.material} <span className="text-xs text-stone-400">{b.material_code}</span>
                </td>
                <td className={td}>{b.supplier}</td>
                <td className={tdNum}>
                  {num(b.qty)} <span className="text-stone-400">{b.unit}</span>
                </td>
                <td className={tdNum}>{num(b.remaining_qty)}</td>
                <td className={tdNum}>{num(b.reserved_qty)}</td>
                <td className={`${tdNum} font-medium`}>{num(b.free_qty)}</td>
                <td className={tdNum}>{num(b.price)}</td>
                <td className={td}>{b.currency}</td>
                <td className={tdNum}>{money(b.unit_cost_rub, '')}</td>
                <td className={td}>
                  <StatusBadge status={b.status} title={b.status_title} />
                </td>
              </tr>
            ))}
            {data && data.items.length === 0 && (
              <tr>
                <td colSpan={COLUMNS.length} className="px-3 py-8 text-center text-stone-400">
                  Ничего не найдено
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      <div className="mt-3 flex flex-wrap items-center justify-between gap-3 text-sm text-stone-600">
        <div>
          Всего: <b>{data?.total ?? '…'}</b>
        </div>
        <div className="flex items-center gap-2">
          <select
            className="rounded-md border border-stone-300 px-2 py-1"
            value={pageSize}
            onChange={(e) => {
              const next = new URLSearchParams(params)
              next.set('page_size', e.target.value)
              next.set('page', '1')
              setParams(next)
            }}
          >
            {[20, 50, 100].map((n) => (
              <option key={n} value={n}>
                по {n}
              </option>
            ))}
          </select>
          <Button variant="secondary" disabled={page <= 1} onClick={() => setParam('page', String(page - 1))}>
            ←
          </Button>
          <span>
            {page} из {totalPages}
          </span>
          <Button variant="secondary" disabled={page >= totalPages} onClick={() => setParam('page', String(page + 1))}>
            →
          </Button>
        </div>
      </div>
    </div>
  )
}

function ColumnFilter({
  col,
  drafts,
  setDrafts,
}: {
  col: Col
  drafts: Record<string, string>
  setDrafts: (fn: (d: Record<string, string>) => Record<string, string>) => void
}) {
  const set = (k: string, v: string) => setDrafts((d) => ({ ...d, [k]: v }))
  const cls = `${inputCls} py-1 text-xs`
  if (col.filter === 'text')
    return <input className={cls} placeholder="фильтр" value={drafts[col.key] ?? ''} onChange={(e) => set(col.key, e.target.value)} />
  if (col.filter === 'status')
    return (
      <select className={cls} value={drafts.status} onChange={(e) => set('status', e.target.value)}>
        <option value="">все</option>
        <option value="on_check">На проверке</option>
        <option value="accepted">Принята</option>
        <option value="rejected">Брак</option>
      </select>
    )
  if (col.filter === 'currency')
    return (
      <select className={cls} value={drafts.currency} onChange={(e) => set('currency', e.target.value)}>
        <option value="">все</option>
        <option>RUB</option>
        <option>USD</option>
        <option>EUR</option>
      </select>
    )
  if (col.filter === 'date')
    return (
      <div className="flex flex-col gap-1">
        <input type="date" className={cls} value={drafts.date_from} onChange={(e) => set('date_from', e.target.value)} title="с" />
        <input type="date" className={cls} value={drafts.date_to} onChange={(e) => set('date_to', e.target.value)} title="по" />
      </div>
    )
  return null
}
