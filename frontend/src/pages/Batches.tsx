import { PackageSearch, Plus, RotateCcw, Search } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { api } from '@/api'
import { useAuth } from '@/auth'
import { Page } from '@/components/layout/AppShell'
import {
  Banner,
  BatchStatusBadge,
  Button,
  Card,
  DateRange,
  DocLink,
  EmptyState,
  FilterRow,
  Input,
  MaterialCode,
  PageHeader,
  Pagination,
  Qty,
  Select,
  Table,
  TableScroll,
  TableSkeleton,
  Td,
  Th,
  Tr,
} from '@/components/ui'
import { cn } from '@/lib/cn'
import { formatDate, formatMoney, formatPrice, formatQty } from '@/lib/format'
import type { BatchRow, Page as PageData } from '@/types'

const TEXT_FILTERS = ['number', 'material', 'supplier'] as const
const ALL_FILTERS = [...TEXT_FILTERS, 'status', 'currency', 'date_from', 'date_to']

/**
 * 02–03 — Реестр партий. Фильтры, сортировка и страница живут в URL (ссылкой можно поделиться),
 * фильтрует и листает сервер.
 */
export default function BatchesPage() {
  const navigate = useNavigate()
  const { can } = useAuth()
  const [params, setParams] = useSearchParams()
  const [data, setData] = useState<PageData<BatchRow> | null>(null)
  const [error, setError] = useState<string | null>(null)
  // Текстовые фильтры применяются с задержкой, чтобы не дёргать сервер на каждую букву.
  const [drafts, setDrafts] = useState<Record<string, string>>(() =>
    Object.fromEntries(TEXT_FILTERS.map((k) => [k, params.get(k) ?? ''])),
  )

  const sort = params.get('sort') ?? 'received_date'
  const direction = (params.get('direction') ?? 'desc') as 'asc' | 'desc'
  const page = Number(params.get('page') ?? 1)
  const pageSize = Number(params.get('page_size') ?? 20)
  const query = params.toString()

  useEffect(() => {
    const q = new URLSearchParams(query)
    if (!q.get('sort')) q.set('sort', 'received_date')
    api<PageData<BatchRow>>(`/api/batches?${q}`)
      .then((d) => {
        setData(d)
        setError(null)
      })
      .catch((e) => setError(e.message))
  }, [query])

  useEffect(() => {
    const t = setTimeout(() => {
      const next = new URLSearchParams(params)
      let changed = false
      for (const k of TEXT_FILTERS) {
        const v = drafts[k].trim()
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

  function setParam(patch: Record<string, string | null>, resetPage = true) {
    const next = new URLSearchParams(params)
    for (const [k, v] of Object.entries(patch)) {
      if (v) next.set(k, v)
      else next.delete(k)
    }
    if (resetPage) next.set('page', '1')
    setParams(next)
  }

  function resetFilters() {
    setDrafts(Object.fromEntries(TEXT_FILTERS.map((k) => [k, ''])))
    setParam(Object.fromEntries(ALL_FILTERS.map((k) => [k, null])))
  }

  const hasFilters = ALL_FILTERS.some((k) => params.get(k))

  const th = (key: string, label: string, align: 'left' | 'right' = 'left') => (
    <Th
      align={align}
      sortable
      sort={sort === key ? direction : null}
      onSort={() =>
        setParam({ sort: key, direction: sort === key && direction === 'desc' ? 'asc' : 'desc' })
      }
    >
      {label}
    </Th>
  )

  return (
    <Page wide>
      <PageHeader
        title="Реестр партий"
        subtitle="Все партии сырья от поставщиков. Себестоимость — в рублях по курсу на дату поступления."
        actions={
          <>
            {hasFilters && (
              <Button variant="ghost" icon={<RotateCcw />} onClick={resetFilters}>
                Сбросить фильтры
              </Button>
            )}
            {can('create_receipt') && (
              <Button variant="primary" icon={<Plus />} onClick={() => navigate('/receipts/new')}>
                Поступление
              </Button>
            )}
          </>
        }
      />
      {error && <Banner tone="error" className="mb-4">{error}</Banner>}

      <Card>
        <TableScroll>
          <Table fixed minWidth={1140}>
            <colgroup>
              <col className="w-[84px]" />
              <col className="w-[106px]" />
              <col />
              <col className="w-[140px]" />
              <col className="w-[84px]" />
              <col className="w-[74px]" />
              <col className="w-[68px]" />
              <col className="w-[80px]" />
              <col className="w-[62px]" />
              <col className="w-[76px]" />
              <col className="w-[92px]" />
              <col className="w-[120px]" />
            </colgroup>
            <thead>
              <tr>
                {th('number', 'Номер')}
                {th('received_date', 'Дата')}
                {th('material', 'Материал')}
                {th('supplier', 'Поставщик')}
                {th('qty', 'Пришло', 'right')}
                {th('remaining_qty', 'Остаток', 'right')}
                {th('reserved_qty', 'Резерв', 'right')}
                {th('free_qty', 'Свободно', 'right')}
                {th('price', 'Цена', 'right')}
                {th('currency', 'Валюта')}
                {th('unit_cost_rub', 'Себест. ₽/ед', 'right')}
                {th('status', 'Статус')}
              </tr>
              <FilterRow>
                <td>
                  <Input
                    size="sm"
                    placeholder="П-…"
                    aria-label="Фильтр по номеру"
                    value={drafts.number}
                    onChange={(e) => setDrafts((d) => ({ ...d, number: e.target.value }))}
                  />
                </td>
                <td>
                  <DateRange
                    size="sm"
                    label="Период поступления"
                    from={params.get('date_from') ?? ''}
                    to={params.get('date_to') ?? ''}
                    onChange={(from, to) => setParam({ date_from: from, date_to: to })}
                  />
                </td>
                <td>
                  <Input
                    size="sm"
                    leftIcon={<Search />}
                    placeholder="Материал или код"
                    aria-label="Фильтр по материалу"
                    value={drafts.material}
                    onChange={(e) => setDrafts((d) => ({ ...d, material: e.target.value }))}
                  />
                </td>
                <td>
                  <Input
                    size="sm"
                    placeholder="Поставщик"
                    aria-label="Фильтр по поставщику"
                    value={drafts.supplier}
                    onChange={(e) => setDrafts((d) => ({ ...d, supplier: e.target.value }))}
                  />
                </td>
                <td />
                <td />
                <td />
                <td />
                <td />
                <td>
                  <Select
                    size="sm"
                    aria-label="Фильтр по валюте"
                    value={params.get('currency') ?? ''}
                    onChange={(e) => setParam({ currency: e.target.value })}
                  >
                    <option value="">Все</option>
                    <option>RUB</option>
                    <option>USD</option>
                    <option>EUR</option>
                  </Select>
                </td>
                <td />
                <td>
                  <Select
                    size="sm"
                    aria-label="Фильтр по статусу"
                    value={params.get('status') ?? ''}
                    onChange={(e) => setParam({ status: e.target.value })}
                  >
                    <option value="">Все</option>
                    <option value="on_check">На проверке</option>
                    <option value="accepted">Принята</option>
                    <option value="rejected">Брак</option>
                  </Select>
                </td>
              </FilterRow>
            </thead>
            <tbody>
              {data?.items.map((b) => {
                const free = Number(b.free_qty)
                return (
                  <Tr key={b.id}>
                    <Td>
                      <DocLink to={`/batches/${b.id}`}>{b.number}</DocLink>
                    </Td>
                    <Td>{formatDate(b.received_date)}</Td>
                    <Td truncate title={`${b.material} · ${b.material_code}`}>
                      {b.material}
                      <MaterialCode>{b.material_code}</MaterialCode>
                    </Td>
                    <Td truncate title={b.supplier}>
                      {b.supplier}
                    </Td>
                    <Td align="right">
                      <Qty value={formatQty(b.qty)} unit={b.unit} />
                    </Td>
                    <Td align="right">{formatQty(b.remaining_qty)}</Td>
                    <Td align="right">{formatQty(b.reserved_qty)}</Td>
                    <Td
                      align="right"
                      className={cn('font-semibold', free === 0 && b.status === 'accepted' && 'text-danger-fg')}
                    >
                      {formatQty(free)}
                    </Td>
                    <Td align="right">{formatPrice(b.price)}</Td>
                    <Td muted>{b.currency}</Td>
                    <Td align="right">{formatMoney(b.unit_cost_rub).replace(' ₽', '')}</Td>
                    <Td>
                      <BatchStatusBadge status={b.status} />
                    </Td>
                  </Tr>
                )
              })}
            </tbody>
          </Table>
        </TableScroll>
        {!data && !error && <TableSkeleton rows={8} cols={8} />}
        {data && data.items.length === 0 && (
          <EmptyState
            icon={<PackageSearch />}
            title="Ничего не найдено"
            description="Под фильтры не подходит ни одна партия."
            action={
              hasFilters && (
                <Button size="sm" onClick={resetFilters}>
                  Сбросить фильтры
                </Button>
              )
            }
          />
        )}
        <Pagination
          total={data?.total ?? 0}
          totalLabel={hasFilters ? 'Найдено' : 'Всего'}
          page={page}
          pageSize={pageSize}
          onPage={(p) => setParam({ page: String(p) }, false)}
          onPageSize={(s) => setParam({ page_size: String(s) })}
        />
      </Card>
    </Page>
  )
}
