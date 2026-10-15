import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { useAuth } from '../auth'
import { Button, ErrorBox, LightDot, PageHeader, StatusBadge, Table, inputCls, td, tdNum, th } from '../components/ui'
import { day, num } from '../format'
import type { OrderRow } from '../types'

const STATUSES = [
  ['draft', 'Черновик'],
  ['planned', 'Запланировано'],
  ['in_progress', 'В работе'],
  ['completed', 'Завершено'],
  ['cancelled', 'Отменено'],
] as const

export default function OrdersPage() {
  const { can } = useAuth()
  const [orders, setOrders] = useState<OrderRow[]>([])
  const [error, setError] = useState<string | null>(null)
  const [status, setStatus] = useState<string>('active')

  useEffect(() => {
    const q = new URLSearchParams()
    const list = status === 'active' ? ['draft', 'planned', 'in_progress'] : status ? [status] : []
    list.forEach((s) => q.append('status', s))
    api<OrderRow[]>(`/api/orders?${q}`)
      .then(setOrders)
      .catch((e) => setError(e.message))
  }, [status])

  return (
    <div>
      <PageHeader
        title="Производственные задания"
        actions={
          can('manage_orders') && (
            <Link to="/orders/new">
              <Button>+ Новое задание</Button>
            </Link>
          )
        }
      />
      <div className="mb-3 w-56">
        <select className={inputCls} value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="active">Активные</option>
          <option value="">Все</option>
          {STATUSES.map(([v, t]) => (
            <option key={v} value={v}>
              {t}
            </option>
          ))}
        </select>
      </div>
      <ErrorBox error={error} />
      <div className="rounded-lg border border-stone-200 bg-white shadow-sm">
        <Table>
          <thead>
            <tr>
              <th className={th}>Резерв</th>
              <th className={th}>Номер</th>
              <th className={th}>Продукт</th>
              <th className={`${th} text-right`}>Кол-во</th>
              <th className={th}>Дата</th>
              <th className={th}>Цех</th>
              <th className={th}>Статус</th>
            </tr>
          </thead>
          <tbody>
            {orders.map((o) => (
              <tr key={o.id} className="hover:bg-wax-50">
                <td className={td}>{['draft', 'planned'].includes(o.status) ? <LightDot light={o.light} /> : null}</td>
                <td className={td}>
                  <Link to={`/orders/${o.id}`} className="font-medium text-wax-700 hover:underline">
                    {o.number}
                  </Link>
                </td>
                <td className={td}>{o.product}</td>
                <td className={tdNum}>{num(o.qty)} шт</td>
                <td className={td}>{day(o.planned_date)}</td>
                <td className={td}>{o.workshop}</td>
                <td className={td}>
                  <StatusBadge status={o.status} title={o.status_title} />
                </td>
              </tr>
            ))}
            {!orders.length && (
              <tr>
                <td colSpan={7} className="px-3 py-8 text-center text-stone-400">
                  Заданий нет
                </td>
              </tr>
            )}
          </tbody>
        </Table>
      </div>
    </div>
  )
}
