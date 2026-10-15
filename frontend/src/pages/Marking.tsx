import { Fragment, useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { useAuth } from '../auth'
import { Button, ErrorBox, PageHeader, StatusBadge, Table, td, th } from '../components/ui'
import { dateTime } from '../format'
import type { Marking } from '../types'

const TITLES = { pending: 'Отправляется', sent: 'Отправлен', failed: 'Не отправлен' }

export default function MarkingPage() {
  const { can } = useAuth()
  const [rows, setRows] = useState<Marking[]>([])
  const [open, setOpen] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(() => {
    api<Marking[]>('/api/marking').then(setRows).catch((e) => setError(e.message))
  }, [])
  useEffect(() => {
    load()
    const t = setInterval(load, 5000)
    return () => clearInterval(t)
  }, [load])

  async function retry(id: number) {
    try {
      await api(`/api/marking/${id}/retry`, { method: 'POST' })
      load()
    } catch (e) {
      setError((e as Error).message)
    }
  }

  return (
    <div className="max-w-5xl">
      <PageHeader
        title="Отправка в сервис маркировки"
        subtitle="Отчёт уходит в фоне после завершения задания. Повторы с растущей паузой, один ключ идемпотентности на отчёт."
      />
      <ErrorBox error={error} />
      <div className="rounded-lg border border-stone-200 bg-white shadow-sm">
        <Table>
          <thead>
            <tr>
              <th className={th}>Задание</th>
              <th className={th}>Статус</th>
              <th className={th}>Попыток</th>
              <th className={th}>Последняя ошибка</th>
              <th className={th}>Следующая попытка / отправлен</th>
              <th className={th}></th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <Fragment key={r.id}>
                <tr className="cursor-pointer hover:bg-wax-50" onClick={() => setOpen(open === r.id ? null : r.id)}>
                  <td className={td}>
                    <Link className="text-wax-700 hover:underline" to={`/orders/${r.order_id}`} onClick={(e) => e.stopPropagation()}>
                      {r.order_number}
                    </Link>
                  </td>
                  <td className={td}>
                    <StatusBadge status={r.status} title={TITLES[r.status]} />
                  </td>
                  <td className={td}>{r.attempts}</td>
                  <td className={`${td} text-stone-500`}>{r.last_error ?? '—'}</td>
                  <td className={td}>{r.status === 'sent' ? dateTime(r.sent_at) : dateTime(r.next_attempt_at)}</td>
                  <td className={td}>
                    {r.status === 'failed' && can('manage_orders') && (
                      <Button variant="secondary" onClick={(e) => { e.stopPropagation(); retry(r.id) }}>
                        Повторить
                      </Button>
                    )}
                  </td>
                </tr>
                {open === r.id && (
                  <tr>
                    <td colSpan={6} className="bg-stone-50 px-4 py-2">
                      <div className="mb-1 font-mono text-xs text-stone-500">Idempotency-Key: {r.idempotency_key}</div>
                      <ul className="font-mono text-xs text-stone-700">
                        {r.attempt_log.map((a) => (
                          <li key={a.attempt_no}>
                            #{a.attempt_no} {dateTime(a.at)} — HTTP {a.status_code ?? '—'} {a.error ?? 'OK'} ({a.duration_ms} мс)
                          </li>
                        ))}
                        {!r.attempt_log.length && <li>попыток ещё не было</li>}
                      </ul>
                    </td>
                  </tr>
                )}
              </Fragment>
            ))}
          </tbody>
        </Table>
      </div>
    </div>
  )
}
