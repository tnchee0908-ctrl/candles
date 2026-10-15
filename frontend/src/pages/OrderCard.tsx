import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../api'
import { useAuth } from '../auth'
import History from '../components/History'
import { Button, Card, ErrorBox, LightDot, Loading, PageHeader, StatusBadge, Table, inputCls, td, tdNum, th } from '../components/ui'
import { day, dateTime, money, num } from '../format'
import type { OrderCard } from '../types'

interface Cost {
  total_cost_rub: string
  cost_per_unit_rub: string
  basis: string
  complete: boolean
}

export default function OrderCardPage() {
  const { id } = useParams()
  const { can } = useAuth()
  const [order, setOrder] = useState<OrderCard | null>(null)
  const [cost, setCost] = useState<Cost | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [actual, setActual] = useState<Record<number, string> | null>(null)

  const load = useCallback(() => {
    api<OrderCard>(`/api/orders/${id}`)
      .then(setOrder)
      .catch((e) => setError(e.message))
    if (can('view_costs'))
      api<Cost>(`/api/orders/${id}/cost`)
        .then(setCost)
        .catch(() => setCost(null))
  }, [id, can])
  useEffect(load, [load])

  // Пока отчёт в маркировку не отправлен, обновляем карточку — видно попытки и паузы между ними.
  useEffect(() => {
    if (order?.marking?.status !== 'pending') return
    const t = setInterval(load, 4000)
    return () => clearInterval(t)
  }, [order?.marking?.status, load])

  async function act(action: string, json?: unknown) {
    setBusy(true)
    setError(null)
    try {
      const card = await api<OrderCard>(`/api/orders/${id}/${action}`, { method: 'POST', json })
      setOrder(card)
      setActual(null)
      load()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  if (!order) return error ? <ErrorBox error={error} /> : <Loading />
  const manage = can('manage_orders')
  const hasDeficit = order.components.some((c) => Number(c.missing_qty) > 0)

  return (
    <div className="max-w-5xl">
      <PageHeader
        title={`Задание ${order.number}`}
        subtitle={
          <span className="flex flex-wrap items-center gap-2">
            <StatusBadge status={order.status} title={order.status_title} />
            {order.product}, {num(order.qty)} шт · {day(order.planned_date)} · цех {order.workshop}
          </span>
        }
        actions={
          manage && (
            <>
              {order.status === 'draft' && (
                <Button disabled={busy} onClick={() => act('plan')}>
                  Запланировать
                </Button>
              )}
              {order.status === 'planned' && hasDeficit && (
                <Button variant="secondary" disabled={busy} onClick={() => act('plan')}>
                  Дорезервировать
                </Button>
              )}
              {order.status === 'planned' && (
                <Button
                  disabled={busy || hasDeficit}
                  title={hasDeficit ? 'Есть дефицит — запуск невозможен' : ''}
                  onClick={() => act('start')}
                >
                  Запустить
                </Button>
              )}
              {order.status === 'in_progress' && !actual && (
                <Button
                  disabled={busy}
                  onClick={() => setActual(Object.fromEntries(order.components.map((c) => [c.material_id, c.required_qty])))}
                >
                  Завершить…
                </Button>
              )}
              {['draft', 'planned'].includes(order.status) && (
                <Button variant="danger" disabled={busy} onClick={() => act('cancel')}>
                  Отменить
                </Button>
              )}
            </>
          )
        }
      />
      <ErrorBox error={error} />

      <Card
        title="Компоненты"
        actions={
          <div className="flex gap-3 text-xs text-stone-500">
            <LightDot light="green" withLabel />
            <LightDot light="yellow" withLabel />
            <LightDot light="red" withLabel />
          </div>
        }
      >
        <Table>
          <thead>
            <tr>
              <th className={th}></th>
              <th className={th}>Материал</th>
              <th className={`${th} text-right`}>Нужно</th>
              <th className={`${th} text-right`}>В резерве</th>
              <th className={`${th} text-right`}>Дефицит</th>
              <th className={`${th} text-right`}>Факт</th>
            </tr>
          </thead>
          <tbody>
            {order.components.map((c) => (
              <tr key={c.material_id}>
                <td className={td}>
                  <LightDot light={c.light} />
                </td>
                <td className={td}>
                  {c.material} <span className="text-xs text-stone-400">{c.material_code}</span>
                </td>
                <td className={tdNum}>
                  {num(c.required_qty)} {c.unit}
                </td>
                <td className={tdNum}>{num(c.reserved_qty)}</td>
                <td className={`${tdNum} ${Number(c.missing_qty) > 0 ? 'font-medium text-red-700' : 'text-stone-400'}`}>
                  {Number(c.missing_qty) > 0 ? num(c.missing_qty) : '—'}
                </td>
                <td className={tdNum}>
                  {actual ? (
                    <input
                      className={`${inputCls} w-28 text-right`}
                      value={actual[c.material_id] ?? ''}
                      onChange={(e) => setActual({ ...actual, [c.material_id]: e.target.value })}
                    />
                  ) : (
                    num(c.actual_qty)
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </Table>
        {actual && (
          <div className="mt-3 flex items-center gap-2">
            <span className="text-sm text-stone-600">
              Введите фактический расход. Перерасход будет досписан из свободного остатка, экономия вернётся в партии.
            </span>
            <Button
              disabled={busy}
              onClick={() =>
                act('complete', {
                  actual: Object.fromEntries(Object.entries(actual).map(([k, v]) => [k, v.replace(',', '.')])),
                })
              }
            >
              Завершить задание
            </Button>
            <Button variant="ghost" onClick={() => setActual(null)}>
              Отмена
            </Button>
          </div>
        )}
      </Card>

      <div className="mt-4 grid gap-4 md:grid-cols-2">
        <Card title={order.status === 'completed' ? 'Списано из партий' : 'Резерв по партиям (FIFO)'}>
          {(order.status === 'completed' ? order.consumptions : order.reservations).length ? (
            <ul className="space-y-1 text-sm">
              {(order.status === 'completed' ? order.consumptions : order.reservations).map((r, i) => {
                const comp = order.components.find((c) => c.material_id === r.material_id)
                return (
                  <li key={i}>
                    <Link className="text-wax-700 hover:underline" to={`/batches/${r.batch_id}`}>
                      {r.batch_number}
                    </Link>{' '}
                    <span className="text-stone-400">от {day(r.received_date)}</span> — {comp?.material}: {num(r.qty)} {comp?.unit}
                  </li>
                )
              })}
            </ul>
          ) : (
            <div className="text-sm text-stone-400">нет</div>
          )}
        </Card>
        <div className="space-y-4">
          {cost && (
            <Card title="Себестоимость">
              <div className="text-2xl font-semibold">{money(cost.total_cost_rub)}</div>
              <div className="text-sm text-stone-500">
                {money(cost.cost_per_unit_rub)} за шт · {cost.basis}
                {!cost.complete && ' (не весь материал зарезервирован)'}
              </div>
            </Card>
          )}
          {order.marking && (
            <Card title="Отчёт в сервис маркировки">
              <div className="mb-2 flex items-center gap-2 text-sm">
                <StatusBadge
                  status={order.marking.status}
                  title={{ pending: 'Отправляется', sent: 'Отправлен', failed: 'Не отправлен' }[order.marking.status]}
                />
                <span className="text-stone-500">попыток: {order.marking.attempts}</span>
              </div>
              {order.marking.next_attempt_at && (
                <div className="text-xs text-stone-500">Следующая попытка: {dateTime(order.marking.next_attempt_at)}</div>
              )}
              <ul className="mt-2 space-y-0.5 font-mono text-xs text-stone-600">
                {order.marking.attempt_log.map((a) => (
                  <li key={a.attempt_no}>
                    #{a.attempt_no} {dateTime(a.at)} — {a.status_code ?? '—'} {a.error ?? 'OK'} ({a.duration_ms} мс)
                  </li>
                ))}
              </ul>
            </Card>
          )}
        </div>
      </div>

      <div className="mt-4">
        <Card title="История изменений">
          <History entries={order.history} />
        </Card>
      </div>
    </div>
  )
}
