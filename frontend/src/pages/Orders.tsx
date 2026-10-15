import { ClipboardList, Plus } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '@/api'
import { useAuth } from '@/auth'
import { Page } from '@/components/layout/AppShell'
import {
  Banner,
  Button,
  Card,
  DocLink,
  EmptyState,
  OrderStatusBadge,
  PageHeader,
  Qty,
  ReserveDot,
  ReserveLegend,
  Segmented,
  Table,
  TableScroll,
  TableSkeleton,
  Td,
  Th,
  Tr,
} from '@/components/ui'
import { formatDate } from '@/lib/format'
import { reserveLevel } from '@/lib/reserve'
import type { OrderRow } from '@/types'

type Filter = 'active' | 'draft' | 'completed' | 'cancelled' | 'all'

const MATCH: Record<Filter, (s: OrderRow['status']) => boolean> = {
  active: (s) => s === 'planned' || s === 'in_progress' || s === 'draft',
  draft: (s) => s === 'draft',
  completed: (s) => s === 'completed',
  cancelled: (s) => s === 'cancelled',
  all: () => true,
}

/** 08 — Производственные задания: сегментный фильтр, светофор резерва, статус. */
export default function OrdersPage() {
  const navigate = useNavigate()
  const { can } = useAuth()
  const [orders, setOrders] = useState<OrderRow[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [filter, setFilter] = useState<Filter>('active')

  useEffect(() => {
    api<OrderRow[]>('/api/orders')
      .then(setOrders)
      .catch((e) => setError(e.message))
  }, [])

  const all = orders ?? []
  const rows = all.filter((o) => MATCH[filter](o.status))
  const count = (f: Filter) => all.filter((o) => MATCH[f](o.status)).length
  const newOrder = can('manage_orders') && (
    <Button variant="primary" icon={<Plus />} onClick={() => navigate('/orders/new')}>
      Новое задание
    </Button>
  )

  return (
    <Page>
      <PageHeader
        title="Производственные задания"
        subtitle="При планировании материалы резервируются по FIFO — из самых старых принятых партий."
        actions={newOrder}
      />
      {error && <Banner tone="error" className="mb-4">{error}</Banner>}
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <Segmented
          label="Статус заданий"
          value={filter}
          onChange={setFilter}
          options={[
            { value: 'active', label: 'Активные', count: count('active') },
            { value: 'draft', label: 'Черновики', count: count('draft') },
            { value: 'completed', label: 'Завершённые', count: count('completed') },
            { value: 'cancelled', label: 'Отменённые', count: count('cancelled') },
            { value: 'all', label: 'Все', count: all.length },
          ]}
        />
        <ReserveLegend />
      </div>
      <Card>
        <TableScroll>
          <Table minWidth={820}>
            <thead>
              <tr>
                <Th className="w-[150px]">Резерв</Th>
                <Th className="w-[110px]">Номер</Th>
                <Th>Продукт</Th>
                <Th align="right" className="w-[110px]">Кол-во</Th>
                <Th className="w-[150px]">Плановая дата</Th>
                <Th align="right" className="w-[70px]">Цех</Th>
                <Th className="w-[150px]">Статус</Th>
              </tr>
            </thead>
            <tbody>
              {rows.map((o) => {
                const level = reserveLevel(o.light, o.status)
                const waiting = o.status === 'draft' || o.status === 'planned'
                return (
                  <Tr key={o.id} highlight={o.status === 'planned' && level !== 'full'}>
                    <Td>{waiting ? <ReserveDot level={level} showLabel /> : <span className="text-fg-subtle">—</span>}</Td>
                    <Td>
                      <DocLink to={`/orders/${o.id}`}>{o.number}</DocLink>
                    </Td>
                    <Td>
                      {o.product}
                      {o.deficit_summary && (
                        <span className="ml-1.5 text-xs text-danger-fg">дефицит: {o.deficit_summary}</span>
                      )}
                    </Td>
                    <Td align="right">
                      <Qty value={o.qty} unit="шт" />
                    </Td>
                    <Td>{formatDate(o.planned_date)}</Td>
                    <Td align="right">{o.workshop}</Td>
                    <Td>
                      <OrderStatusBadge status={o.status} />
                    </Td>
                  </Tr>
                )
              })}
            </tbody>
          </Table>
        </TableScroll>
        {!orders && !error && <TableSkeleton rows={6} cols={6} />}
        {orders && rows.length === 0 && (
          <EmptyState
            icon={<ClipboardList />}
            title="Заданий нет"
            description="В этом статусе пока нет ни одного задания."
            action={newOrder}
          />
        )}
      </Card>
    </Page>
  )
}
