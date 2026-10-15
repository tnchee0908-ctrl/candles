import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { Button, ErrorBox, PageHeader, Table, inputCls, td, th } from '../components/ui'
import { dateTime } from '../format'
import type { AuditEntry, Page } from '../types'

const ENTITY = { batch: 'Партия', order: 'Задание', material: 'Материал', recipe: 'Рецепт' } as Record<string, string>

function short(v: Record<string, unknown> | null): string {
  if (!v) return '—'
  const { components: _components, ...rest } = v
  void _components
  return Object.entries(rest)
    .map(([k, val]) => `${k}: ${typeof val === 'object' ? JSON.stringify(val) : String(val)}`)
    .join(', ')
}

export default function AuditPage() {
  const [data, setData] = useState<Page<AuditEntry> | null>(null)
  const [entity, setEntity] = useState('')
  const [page, setPage] = useState(1)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const q = new URLSearchParams({ page: String(page), page_size: '50' })
    if (entity) q.set('entity_type', entity)
    api<Page<AuditEntry>>(`/api/audit?${q}`).then(setData).catch((e) => setError(e.message))
  }, [entity, page])

  const pages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1
  return (
    <div>
      <PageHeader title="Журнал изменений" subtitle="Кто, когда, что было и что стало" />
      <ErrorBox error={error} />
      <div className="mb-3 w-48">
        <select className={inputCls} value={entity} onChange={(e) => { setEntity(e.target.value); setPage(1) }}>
          <option value="">Все объекты</option>
          {Object.entries(ENTITY).map(([k, v]) => (
            <option key={k} value={k}>
              {v}
            </option>
          ))}
        </select>
      </div>
      <div className="rounded-lg border border-stone-200 bg-white shadow-sm">
        <Table>
          <thead>
            <tr>
              <th className={th}>Когда</th>
              <th className={th}>Кто</th>
              <th className={th}>Объект</th>
              <th className={th}>Действие</th>
              <th className={th}>Было</th>
              <th className={th}>Стало</th>
            </tr>
          </thead>
          <tbody>
            {data?.items.map((e) => (
              <tr key={e.id} className="align-top">
                <td className={td}>{dateTime(e.at)}</td>
                <td className={td}>
                  {e.user_full_name}
                  {e.via_assistant && <div className="text-xs text-violet-700">через ассистента</div>}
                </td>
                <td className={td}>
                  {ENTITY[e.entity_type] ?? e.entity_type}{' '}
                  {e.entity_type === 'batch' || e.entity_type === 'order' ? (
                    <Link className="text-wax-700 hover:underline" to={`/${e.entity_type === 'batch' ? 'batches' : 'orders'}/${e.entity_id}`}>
                      {e.entity_label}
                    </Link>
                  ) : (
                    e.entity_label
                  )}
                </td>
                <td className={td}>{e.action}</td>
                <td className={`${td} max-w-xs whitespace-normal font-mono text-xs text-stone-500`}>{short(e.before)}</td>
                <td className={`${td} max-w-xs whitespace-normal font-mono text-xs`}>{short(e.after)}</td>
              </tr>
            ))}
          </tbody>
        </Table>
      </div>
      <div className="mt-3 flex items-center gap-2 text-sm">
        <Button variant="secondary" disabled={page <= 1} onClick={() => setPage(page - 1)}>
          ←
        </Button>
        {page} из {pages}
        <Button variant="secondary" disabled={page >= pages} onClick={() => setPage(page + 1)}>
          →
        </Button>
      </div>
    </div>
  )
}
