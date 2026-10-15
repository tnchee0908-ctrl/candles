import { Search } from 'lucide-react'
import { useEffect, useState } from 'react'
import { api } from '@/api'
import { Page } from '@/components/layout/AppShell'
import {
  Banner,
  Card,
  Dash,
  DocLink,
  Input,
  MaterialCode,
  PageHeader,
  Qty,
  Table,
  TableScroll,
  TableSkeleton,
  Td,
  Th,
  Tr,
} from '@/components/ui'
import { cn } from '@/lib/cn'
import { formatQty } from '@/lib/format'
import type { StockRow } from '@/types'

/** 06 — Остатки: «Свободно» — акцент, ноль — красным. */
export default function StockPage() {
  const [rows, setRows] = useState<StockRow[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [q, setQ] = useState('')

  useEffect(() => {
    api<StockRow[]>('/api/stock')
      .then(setRows)
      .catch((e) => setError(e.message))
  }, [])

  const visible = (rows ?? []).filter((r) =>
    `${r.material} ${r.material_code}`.toLowerCase().includes(q.trim().toLowerCase()),
  )

  return (
    <Page>
      <PageHeader
        title="Остатки материалов"
        subtitle="Только принятые партии. «Ждёт приёмки» — партии на проверке, их пока нельзя резервировать."
        actions={
          <div className="w-[260px]">
            <Input
              leftIcon={<Search />}
              placeholder="Материал или код"
              aria-label="Поиск материала"
              value={q}
              onChange={(e) => setQ(e.target.value)}
            />
          </div>
        }
      />
      {error && <Banner tone="error" className="mb-4">{error}</Banner>}
      <Card>
        <TableScroll>
          <Table minWidth={760}>
            <thead>
              <tr>
                <Th>Материал</Th>
                <Th align="right" className="w-[140px]">На складе</Th>
                <Th align="right" className="w-[120px]">В резерве</Th>
                <Th align="right" className="w-[120px]">Свободно</Th>
                <Th align="right" className="w-[140px]">Ждёт приёмки</Th>
                <Th align="right" className="w-[90px]">Партий</Th>
              </tr>
            </thead>
            <tbody>
              {visible.map((r) => (
                <Tr key={r.material_code}>
                  <Td>
                    <DocLink to={`/batches?material=${encodeURIComponent(r.material_code)}`}>{r.material}</DocLink>
                    <MaterialCode>{r.material_code}</MaterialCode>
                  </Td>
                  <Td align="right">
                    <Qty value={formatQty(r.on_hand)} unit={r.unit} />
                  </Td>
                  <Td align="right">{formatQty(r.reserved)}</Td>
                  <Td align="right" className={cn('font-semibold', Number(r.free) <= 0 && 'text-danger-fg')}>
                    {formatQty(r.free)}
                  </Td>
                  <Td align="right">
                    {Number(r.awaiting_inspection) > 0 ? (
                      <DocLink to={`/batches?material=${encodeURIComponent(r.material_code)}&status=on_check`}>
                        {formatQty(r.awaiting_inspection)} {r.unit}
                      </DocLink>
                    ) : (
                      <Dash />
                    )}
                  </Td>
                  <Td align="right">{r.batches_with_stock}</Td>
                </Tr>
              ))}
            </tbody>
          </Table>
        </TableScroll>
        {!rows && !error && <TableSkeleton rows={8} cols={6} />}
        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border py-2.5 pl-4 pr-3 text-sm text-fg-secondary">
          <span>
            Материалов: <b className="font-semibold text-fg">{visible.length}</b>
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="size-2 rounded-full bg-danger-dot" aria-hidden />
            Свободно = 0 — новые задания по этому материалу получат дефицит
          </span>
        </div>
      </Card>
    </Page>
  )
}
