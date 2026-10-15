import { ChevronDown, ChevronRight, RefreshCw, ScanBarcode } from 'lucide-react'
import { Fragment, useCallback, useEffect, useState } from 'react'
import { api } from '@/api'
import { useAuth } from '@/auth'
import { Page } from '@/components/layout/AppShell'
import {
  Banner,
  Button,
  Card,
  DocLink,
  EmptyState,
  IconButton,
  MarkingStatusBadge,
  PageHeader,
  Qty,
  Segmented,
  Table,
  TableScroll,
  TableSkeleton,
  Td,
  Th,
  Tr,
} from '@/components/ui'
import { formatDateTime, formatQty } from '@/lib/format'
import { attemptNote } from '@/lib/marking'
import type { Marking } from '@/types'

type Filter = 'all' | Marking['status']
const badgeStatus = (s: Marking['status']) => (s === 'pending' ? 'sending' : s)

/** 15 — Маркировка: таблица отправок, раскрывающаяся строка с ключом и журналом попыток. */
export default function MarkingPage() {
  const { can } = useAuth()
  const [rows, setRows] = useState<Marking[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [filter, setFilter] = useState<Filter>('all')
  const [open, setOpen] = useState<number | null>(null)
  const [retrying, setRetrying] = useState<number | null>(null)

  const load = useCallback(() => {
    api<Marking[]>('/api/marking')
      .then((r) => {
        setRows(r)
        setError(null)
      })
      .catch((e) => setError(e.message))
  }, [])

  useEffect(() => {
    load()
    const t = setInterval(load, 5000)
    return () => clearInterval(t)
  }, [load])

  async function retry(id: number) {
    setRetrying(id)
    try {
      await api(`/api/marking/${id}/retry`, { method: 'POST' })
      load()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setRetrying(null)
    }
  }

  const all = rows ?? []
  const visible = all.filter((m) => filter === 'all' || m.status === filter)
  const cnt = (s: Marking['status']) => all.filter((m) => m.status === s).length

  return (
    <Page>
      <PageHeader
        title="Маркировка"
        subtitle="Отчёты о выпуске в сервис маркировки. Повторная отправка безопасна: ключ идемпотентности не меняется."
      />
      {error && <Banner tone="error" className="mb-4">{error}</Banner>}
      <div className="mb-3">
        <Segmented
          label="Статус отправки"
          value={filter}
          onChange={setFilter}
          options={[
            { value: 'all', label: 'Все', count: all.length },
            { value: 'failed', label: 'Не отправлен', count: cnt('failed') },
            { value: 'pending', label: 'Отправляется', count: cnt('pending') },
            { value: 'sent', label: 'Отправлен', count: cnt('sent') },
          ]}
        />
      </div>
      <Card>
        <TableScroll>
          <Table minWidth={940}>
            <thead>
              <tr>
                <Th className="w-10">
                  <span className="sr-only">Раскрыть</span>
                </Th>
                <Th className="w-[100px]">Задание</Th>
                <Th>Продукт</Th>
                <Th align="right" className="w-[90px]">Кол-во</Th>
                <Th className="w-[150px]">Завершено</Th>
                <Th className="w-[150px]">Статус</Th>
                <Th align="right" className="w-[80px]">Попыток</Th>
                <Th className="w-[240px]">Последняя попытка</Th>
                <Th className="w-[120px]" />
              </tr>
            </thead>
            <tbody>
              {visible.map((m) => {
                const last = m.attempt_log[m.attempt_log.length - 1]
                const expanded = open === m.id
                return (
                  <Fragment key={m.id}>
                    <Tr highlight={m.status === 'failed'} className={expanded ? '[&>td]:bg-subtle' : undefined}>
                      <Td>
                        <IconButton
                          label={expanded ? 'Свернуть' : 'Раскрыть'}
                          size="sm"
                          aria-expanded={expanded}
                          onClick={() => setOpen(expanded ? null : m.id)}
                        >
                          {expanded ? <ChevronDown /> : <ChevronRight />}
                        </IconButton>
                      </Td>
                      <Td>
                        <DocLink to={`/orders/${m.order_id}`}>{m.order_number}</DocLink>
                      </Td>
                      <Td>{m.product ?? '—'}</Td>
                      <Td align="right">{m.qty != null ? <Qty value={formatQty(m.qty)} unit="шт" /> : '—'}</Td>
                      <Td>{m.completed_at ? formatDateTime(m.completed_at) : '—'}</Td>
                      <Td>
                        <MarkingStatusBadge status={badgeStatus(m.status)} />
                      </Td>
                      <Td align="right">{m.attempts}</Td>
                      <Td>
                        {m.status === 'pending' && m.next_attempt_at ? (
                          <span className="text-xs text-fg-muted">
                            {last ? `${last.status_code ?? 'нет ответа'} · ` : ''}следующая в{' '}
                            {formatDateTime(m.next_attempt_at).split(', ')[1]}
                          </span>
                        ) : last ? (
                          <>
                            <span className="font-mono text-xs">
                              {last.status_code ?? '—'}
                              {last.status_code && last.status_code < 300 ? ' OK' : ''}
                            </span>{' '}
                            <span className="text-xs text-fg-muted">· {attemptNote(last, formatDateTime(last.at))}</span>
                          </>
                        ) : (
                          <span className="text-xs text-fg-muted">ещё не было</span>
                        )}
                      </Td>
                      <Td align="right">
                        {m.status === 'failed' && can('manage_orders') && (
                          <Button size="sm" icon={<RefreshCw />} loading={retrying === m.id} onClick={() => retry(m.id)}>
                            Повторить
                          </Button>
                        )}
                      </Td>
                    </Tr>
                    {expanded && (
                      <tr>
                        <td colSpan={9} className="border-b border-border-soft bg-subtle pb-4 pl-[52px] pr-4">
                          <div className="rounded border border-border bg-surface">
                            <div className="flex items-center justify-between border-b border-border-soft px-3.5 py-2.5 text-sm">
                              <span className="text-fg-muted">Ключ идемпотентности</span>
                              <span className="font-mono text-xs">{m.idempotency_key}</span>
                            </div>
                            {m.attempt_log.length ? (
                              <Table>
                                <thead>
                                  <tr>
                                    <Th className="w-11">#</Th>
                                    <Th>Время</Th>
                                    <Th>HTTP</Th>
                                    <Th>Ошибка</Th>
                                    <Th align="right">Длительность</Th>
                                  </tr>
                                </thead>
                                <tbody>
                                  {m.attempt_log.map((a) => (
                                    <Tr key={a.attempt_no}>
                                      <Td muted>{a.attempt_no}</Td>
                                      <Td>{formatDateTime(a.at)}</Td>
                                      <Td>
                                        <span className="inline-flex items-center gap-1.5">
                                          <span
                                            className={`size-2 rounded-full ${a.status_code && a.status_code < 300 ? 'bg-success-dot' : 'bg-danger-dot'}`}
                                            aria-hidden
                                          />
                                          <span className="font-mono text-xs">{a.status_code ?? '—'}</span>
                                        </span>
                                      </Td>
                                      <Td muted>{attemptNote(a, '—')}</Td>
                                      <Td align="right">
                                        <Qty value={formatQty(a.duration_ms)} unit="мс" />
                                      </Td>
                                    </Tr>
                                  ))}
                                </tbody>
                              </Table>
                            ) : (
                              <div className="px-3.5 py-3 text-sm text-fg-muted">Попыток ещё не было.</div>
                            )}
                          </div>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                )
              })}
            </tbody>
          </Table>
        </TableScroll>
        {!rows && !error && <TableSkeleton rows={6} cols={7} />}
        {rows && visible.length === 0 && (
          <EmptyState icon={<ScanBarcode />} title="Отправок нет" description="Отчёт появляется после завершения задания." />
        )}
      </Card>
    </Page>
  )
}
