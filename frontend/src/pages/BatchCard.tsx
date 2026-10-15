import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../api'
import { useAuth } from '../auth'
import History from '../components/History'
import { Button, Card, ErrorBox, Loading, PageHeader, StatusBadge } from '../components/ui'
import { day, dateTime, money, num } from '../format'
import type { BatchCard } from '../types'

export default function BatchCardPage() {
  const { id } = useParams()
  const { can } = useAuth()
  const [card, setCard] = useState<BatchCard | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const load = useCallback(() => {
    api<BatchCard>(`/api/batches/${id}`).then(setCard).catch((e) => setError(e.message))
  }, [id])
  useEffect(load, [load])

  async function setStatus(status: 'accepted' | 'rejected') {
    setBusy(true)
    setError(null)
    try {
      await api(`/api/batches/${id}/status`, { method: 'POST', json: { status } })
      load()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  if (!card) return error ? <ErrorBox error={error} /> : <Loading />
  const b = card.batch
  return (
    <div className="max-w-5xl">
      <PageHeader
        title={`Партия ${b.number}`}
        subtitle={
          <>
            {b.material} · поступление {card.receipt_number} от {day(b.received_date)} · {b.supplier}
          </>
        }
        actions={
          b.status === 'on_check' &&
          can('set_batch_status') && (
            <>
              <Button disabled={busy} onClick={() => setStatus('accepted')}>
                Принять
              </Button>
              <Button variant="danger" disabled={busy} onClick={() => setStatus('rejected')}>
                Брак
              </Button>
            </>
          )
        }
      />
      <ErrorBox error={error} />
      <div className="grid gap-4 md:grid-cols-2">
        <Card title="Сведения">
          <dl className="grid grid-cols-2 gap-y-2 text-sm">
            <dt className="text-stone-500">Статус</dt>
            <dd>
              <StatusBadge status={b.status} title={b.status_title} />
            </dd>
            <dt className="text-stone-500">Пришло</dt>
            <dd>
              {num(b.qty)} {b.unit}
            </dd>
            <dt className="text-stone-500">Остаток</dt>
            <dd>
              {num(b.remaining_qty)} {b.unit}
            </dd>
            <dt className="text-stone-500">В резерве</dt>
            <dd>
              {num(b.reserved_qty)} {b.unit}
            </dd>
            <dt className="text-stone-500">Свободно</dt>
            <dd className="font-medium">
              {num(b.free_qty)} {b.unit}
            </dd>
            <dt className="text-stone-500">Цена</dt>
            <dd>
              {num(b.price)} {b.currency} за {b.unit}
            </dd>
            <dt className="text-stone-500">Курс</dt>
            <dd>
              {b.currency === 'RUB' ? '—' : `${num(b.rate)} ₽ на ${day(b.rate_date)}`}
              {b.rate_date !== b.received_date && b.currency !== 'RUB' && (
                <div className="text-xs text-stone-500">поставка в нерабочий день — взят последний курс</div>
              )}
            </dd>
            <dt className="text-stone-500">Себестоимость</dt>
            <dd>{money(b.unit_cost_rub)} за {b.unit}</dd>
          </dl>
          {b.comment && (
            <div className="mt-3 rounded-md bg-stone-50 p-2 text-sm text-stone-700">
              <div className="text-xs text-stone-500">Комментарий</div>
              {b.comment}
            </div>
          )}
        </Card>
        <Card title="Движения">
          <h3 className="mb-1 text-xs font-semibold uppercase text-stone-500">Резервы</h3>
          {card.reservations.length ? (
            <ul className="mb-3 text-sm">
              {card.reservations.map((r) => (
                <li key={r.order_id}>
                  <Link className="text-wax-700 hover:underline" to={`/orders/${r.order_id}`}>
                    {r.order_number}
                  </Link>{' '}
                  — {num(r.qty)} {b.unit}
                </li>
              ))}
            </ul>
          ) : (
            <div className="mb-3 text-sm text-stone-400">нет</div>
          )}
          <h3 className="mb-1 text-xs font-semibold uppercase text-stone-500">Списания</h3>
          {card.consumptions.length ? (
            <ul className="text-sm">
              {card.consumptions.map((c, i) => (
                <li key={i}>
                  <Link className="text-wax-700 hover:underline" to={`/orders/${c.order_id}`}>
                    {c.order_number}
                  </Link>{' '}
                  — {num(c.qty)} {b.unit} <span className="text-stone-400">{dateTime(c.at)}</span>
                </li>
              ))}
            </ul>
          ) : (
            <div className="text-sm text-stone-400">нет</div>
          )}
        </Card>
      </div>
      <div className="mt-4">
        <Card title="История изменений">
          <History entries={card.history} />
        </Card>
      </div>
    </div>
  )
}
