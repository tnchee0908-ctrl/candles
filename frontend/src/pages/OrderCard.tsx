import { Check, Info, Play, RefreshCw, X } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { api } from '@/api'
import { useAuth } from '@/auth'
import { Page } from '@/components/layout/AppShell'
import {
  Badge,
  Banner,
  Button,
  Card,
  CardBody,
  CardFooter,
  CardHeader,
  CardSkeleton,
  Dash,
  DocLink,
  Input,
  MarkingStatusBadge,
  MaterialCode,
  Metric,
  OrderStatusBadge,
  PageHeader,
  Qty,
  ReserveDot,
  ReserveLegend,
  Table,
  TableScroll,
  Td,
  Th,
  Timeline,
  Tr,
} from '@/components/ui'
import { auditToEvent } from '@/lib/audit'
import { attemptNote } from '@/lib/marking'
import { formatDate, formatDateTime, formatMoney, formatQty } from '@/lib/format'
import { reserveLevel } from '@/lib/reserve'
import type { Component, OrderCard } from '@/types'

interface Cost {
  total_cost_rub: string
  cost_per_unit_rub: string | null
  basis: string
  complete: boolean
}

type Action = 'plan' | 'start' | 'cancel' | 'complete'

const parseNum = (v: string) => Number(v.replace(/\s/g, '').replace(',', '.'))

/** 09–12 — Карточка задания. Действия и блоки зависят от статуса. */
export default function OrderCardPage() {
  const { id } = useParams()
  const { can } = useAuth()
  const [order, setOrder] = useState<OrderCard | null>(null)
  const [cost, setCost] = useState<Cost | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState<Action | null>(null)
  const [facts, setFacts] = useState<Record<number, string>>({})

  const load = useCallback(() => {
    api<OrderCard>(`/api/orders/${id}`)
      .then((o) => {
        setOrder(o)
        setFacts(Object.fromEntries(o.components.map((c) => [c.material_id, formatQty(c.required_qty)])))
      })
      .catch((e) => setError(e.message))
    if (can('view_costs'))
      api<Cost>(`/api/orders/${id}/cost`)
        .then(setCost)
        .catch(() => setCost(null))
  }, [id, can])
  useEffect(load, [load])

  // Пока отчёт в маркировку не отправлен, обновляем карточку — видно попытки и паузы между ними.
  const markingPending = order?.marking?.status === 'pending'
  useEffect(() => {
    if (!markingPending) return
    const t = setInterval(() => {
      api<OrderCard>(`/api/orders/${id}`)
        .then((o) => setOrder((prev) => (prev ? { ...prev, marking: o.marking } : o)))
        .catch(() => undefined)
    }, 4000)
    return () => clearInterval(t)
  }, [markingPending, id])

  async function act(action: Action, json?: unknown) {
    setBusy(action)
    setError(null)
    try {
      await api<OrderCard>(`/api/orders/${id}/${action}`, { method: 'POST', json })
      load()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(null)
    }
  }

  if (!order) {
    return (
      <Page>
        {error ? (
          <Banner tone="error">{error}</Banner>
        ) : (
          <div className="flex flex-col gap-4">
            <CardSkeleton lines={7} />
            <CardSkeleton lines={4} />
          </div>
        )}
      </Page>
    )
  }

  const manage = can('manage_orders')
  const isDraft = order.status === 'draft'
  const isPlanned = order.status === 'planned'
  const inProgress = order.status === 'in_progress'
  const completed = order.status === 'completed'
  const deficits = order.components.filter((c) => Number(c.missing_qty) > 0)
  const hasDeficit = isPlanned && deficits.length > 0
  const factInvalid = order.components.some((c) => !(parseNum(facts[c.material_id] ?? '') >= 0))
  const byMaterial = Object.fromEntries(order.components.map((c) => [c.material_id, c]))
  const movements = completed ? order.consumptions : order.reservations
  const history = order.history.map((e) => auditToEvent(e, { unit: 'шт' }))

  const actions = manage && (
    <>
      {(isDraft || isPlanned) && (
        <Button variant="danger" loading={busy === 'cancel'} disabled={busy !== null} onClick={() => act('cancel')}>
          Отменить
        </Button>
      )}
      {isDraft && (
        <Button variant="primary" loading={busy === 'plan'} disabled={busy !== null} onClick={() => act('plan')}>
          Запланировать
        </Button>
      )}
      {hasDeficit && (
        <Button icon={<RefreshCw />} loading={busy === 'plan'} disabled={busy !== null} onClick={() => act('plan')}>
          Дорезервировать
        </Button>
      )}
      {isPlanned && (
        <Button
          variant="primary"
          icon={<Play />}
          loading={busy === 'start'}
          disabled={busy !== null}
          disabledReason={hasDeficit ? 'Есть дефицит — запуск невозможен' : undefined}
          onClick={() => act('start')}
        >
          Запустить
        </Button>
      )}
    </>
  )

  const diffCell = (c: Component) => {
    const fact = completed ? Number(c.actual_qty ?? c.required_qty) : parseNum(facts[c.material_id] ?? '')
    if (!Number.isFinite(fact)) return <Dash />
    const diff = Math.round((fact - Number(c.required_qty)) * 10000) / 10000
    if (diff > 0)
      return (
        <span className="text-warning-fg">
          +{formatQty(diff)} {c.unit} — {completed ? 'досписано' : 'досписать'} из свободного остатка
        </span>
      )
    if (diff < 0)
      return (
        <span className="text-success-fg">
          −{formatQty(-diff)} {c.unit} — {completed ? 'вернулось' : 'вернётся'} в партию
        </span>
      )
    return <Dash />
  }

  return (
    <Page>
      <PageHeader
        breadcrumbs={[{ label: 'Задания', to: '/orders' }, { label: order.number }]}
        title={`Задание ${order.number}`}
        badge={<OrderStatusBadge status={order.status} />}
        subtitle={`${order.product} · ${formatQty(order.qty)} шт · ${formatDate(order.planned_date)} · Цех ${order.workshop}`}
        actions={actions}
      />

      <div className="flex flex-col gap-4">
        {error && (
          <Banner tone="error" onDismiss={() => setError(null)}>
            {error}
          </Banner>
        )}
        {hasDeficit && (
          <Banner
            tone="warning"
            title={`Не хватает ${deficits
              .map((c) => `${formatQty(c.missing_qty)} ${c.unit} «${c.material}»`)
              .join(', ')}.`}
          >
            После приёмки новой партии нажмите «Дорезервировать».
          </Banner>
        )}
        {order.comment && <Banner tone="info">{order.comment}</Banner>}

        <Card className={inProgress && manage ? 'border-accent-200' : undefined}>
          <CardHeader
            title={inProgress && manage ? 'Завершение: фактический расход' : 'Компоненты'}
            description={
              inProgress && manage
                ? 'Перерасход будет досписан из свободного остатка, экономия вернётся в партии.'
                : undefined
            }
            actions={(isDraft || isPlanned) && <ReserveLegend />}
          />
          <TableScroll>
            <Table minWidth={720}>
              <thead>
                <tr>
                  {!completed && (
                    <Th className="w-11">
                      <span className="sr-only">Резерв</span>
                    </Th>
                  )}
                  <Th>Материал</Th>
                  <Th align="right" className="w-[130px]">
                    {completed ? 'Нужно по норме' : 'Нужно'}
                  </Th>
                  {!completed && (
                    <Th align="right" className="w-[120px]">
                      В резерве
                    </Th>
                  )}
                  {isPlanned && (
                    <Th align="right" className="w-[130px]">
                      Дефицит
                    </Th>
                  )}
                  {(inProgress || completed) && (
                    <Th align="right" className="w-[170px]">
                      {completed ? 'Списано (факт)' : 'Факт'}
                    </Th>
                  )}
                  {(inProgress || completed) && <Th className="w-[260px]">Отклонение</Th>}
                </tr>
              </thead>
              <tbody>
                {order.components.map((c) => (
                  <Tr key={c.material_id} highlight={isPlanned && Number(c.missing_qty) > 0}>
                    {!completed && (
                      <Td>
                        <ReserveDot level={reserveLevel(c.light, order.status)} />
                      </Td>
                    )}
                    <Td>
                      {c.material}
                      <MaterialCode>{c.material_code}</MaterialCode>
                    </Td>
                    <Td align="right">
                      <Qty value={formatQty(c.required_qty)} unit={c.unit} />
                    </Td>
                    {!completed && <Td align="right">{formatQty(c.reserved_qty)}</Td>}
                    {isPlanned && (
                      <Td align="right">
                        {Number(c.missing_qty) > 0 ? (
                          <span className="font-semibold text-danger-fg">
                            {formatQty(c.missing_qty)} <span className="font-normal">{c.unit}</span>
                          </span>
                        ) : (
                          <Dash />
                        )}
                      </Td>
                    )}
                    {inProgress && (
                      <Td align="right" className="py-1">
                        {manage ? (
                          <Input
                            numeric
                            suffix={c.unit}
                            aria-label={`Факт: ${c.material}`}
                            invalid={!(parseNum(facts[c.material_id] ?? '') >= 0)}
                            value={facts[c.material_id] ?? ''}
                            onChange={(e) => setFacts((f) => ({ ...f, [c.material_id]: e.target.value }))}
                          />
                        ) : (
                          <Dash />
                        )}
                      </Td>
                    )}
                    {completed && (
                      <Td align="right">
                        <Qty value={formatQty(c.actual_qty ?? c.required_qty)} unit={c.unit} />
                      </Td>
                    )}
                    {(inProgress || completed) && <Td className="text-sm">{manage || completed ? diffCell(c) : <Dash />}</Td>}
                  </Tr>
                ))}
              </tbody>
            </Table>
          </TableScroll>
          {inProgress && manage && (
            <CardFooter className="bg-accent-25">
              <span className="flex items-center gap-2 text-sm text-fg-secondary">
                <Info className="size-3.5" aria-hidden />
                Отчёт в сервис маркировки отправится автоматически.
              </span>
              <div className="flex gap-2">
                <Button
                  variant="ghost"
                  icon={<X />}
                  disabled={busy !== null}
                  onClick={() =>
                    setFacts(Object.fromEntries(order.components.map((c) => [c.material_id, formatQty(c.required_qty)])))
                  }
                >
                  Сбросить к норме
                </Button>
                <Button
                  variant="primary"
                  icon={<Check />}
                  loading={busy === 'complete'}
                  disabledReason={factInvalid ? 'Проверьте фактический расход' : undefined}
                  onClick={() =>
                    act('complete', {
                      actual: Object.fromEntries(
                        order.components.map((c) => [c.material_id, String(parseNum(facts[c.material_id] ?? ''))]),
                      ),
                    })
                  }
                >
                  Завершить задание
                </Button>
              </div>
            </CardFooter>
          )}
        </Card>

        <div className="grid grid-cols-[repeat(auto-fit,minmax(min(100%,380px),1fr))] items-start gap-4">
          <Card>
            <CardHeader
              title={completed ? 'Списано из партий' : 'Резерв по партиям (FIFO)'}
              actions={!completed && <span className="text-xs text-fg-muted">старые партии — первыми</span>}
            />
            {movements.length ? (
              <Table>
                <thead>
                  <tr>
                    <Th>Партия</Th>
                    <Th>Поступила</Th>
                    <Th>Материал</Th>
                    <Th align="right">Кол-во</Th>
                  </tr>
                </thead>
                <tbody>
                  {movements.map((r, i) => (
                    <Tr key={`${r.batch_id}-${r.material_id}-${i}`}>
                      <Td>
                        <DocLink to={`/batches/${r.batch_id}`}>{r.batch_number}</DocLink>
                      </Td>
                      <Td muted>{formatDate(r.received_date)}</Td>
                      <Td>{byMaterial[r.material_id]?.material}</Td>
                      <Td align="right">
                        <Qty value={formatQty(r.qty)} unit={byMaterial[r.material_id]?.unit} />
                      </Td>
                    </Tr>
                  ))}
                </tbody>
              </Table>
            ) : (
              <CardBody className="text-sm text-fg-muted">
                {isDraft ? 'Резерв появится после планирования.' : 'Ничего не зарезервировано.'}
              </CardBody>
            )}
          </Card>

          <div className="flex flex-col gap-4">
            {cost && (
              <Card>
                <CardHeader
                  title="Себестоимость"
                  actions={
                    completed ? (
                      <Badge tone="success">итог</Badge>
                    ) : (
                      <Badge tone={cost.complete ? 'neutral' : 'warning'}>оценка</Badge>
                    )
                  }
                />
                <CardBody>
                  <Metric
                    value={formatMoney(cost.total_cost_rub)}
                    caption={
                      cost.cost_per_unit_rub && (
                        <>
                          {formatMoney(cost.cost_per_unit_rub)} <span className="text-fg-muted">за 1 шт</span>
                        </>
                      )
                    }
                  />
                  <p className="mt-3.5 border-t border-border-soft pt-3 text-sm text-fg-secondary">
                    {completed
                      ? 'Основа расчёта: фактическое списание из партий по их себестоимости в рублях.'
                      : !cost.complete
                        ? 'Посчитано по текущему резерву. Зарезервирован не весь материал — итог вырастет после дорезервирования.'
                        : 'Посчитано по текущему резерву. Итог зафиксируется по фактическому списанию при завершении.'}
                  </p>
                </CardBody>
              </Card>
            )}

            {order.marking && (
              <Card>
                <CardHeader
                  title="Отчёт в сервис маркировки"
                  actions={
                    <>
                      <MarkingStatusBadge
                        status={order.marking.status === 'pending' ? 'sending' : order.marking.status}
                      />
                      <span className="text-xs text-fg-muted">попыток: {order.marking.attempts}</span>
                    </>
                  }
                />
                {order.marking.attempt_log.length > 0 ? (
                  <Table>
                    <thead>
                      <tr>
                        <Th className="w-9">#</Th>
                        <Th>Время</Th>
                        <Th>Результат</Th>
                        <Th align="right">Длительность</Th>
                      </tr>
                    </thead>
                    <tbody>
                      {order.marking.attempt_log.map((a) => (
                        <Tr key={a.attempt_no}>
                          <Td muted>{a.attempt_no}</Td>
                          <Td>{formatDateTime(a.at)}</Td>
                          <Td>
                            <span className="inline-flex items-center gap-1.5">
                              <span
                                className={`size-2 rounded-full ${a.status_code && a.status_code < 300 ? 'bg-success-dot' : 'bg-danger-dot'}`}
                                aria-hidden
                              />
                              <span className="font-mono text-xs">{a.status_code ? `HTTP ${a.status_code}` : 'нет ответа'}</span>
                              <span className="text-xs text-fg-muted">{attemptNote(a)}</span>
                            </span>
                          </Td>
                          <Td align="right">
                            <Qty value={formatQty(a.duration_ms)} unit="мс" />
                          </Td>
                        </Tr>
                      ))}
                    </tbody>
                  </Table>
                ) : (
                  <CardBody className="text-sm text-fg-muted">Отправка ещё не начиналась.</CardBody>
                )}
                <CardFooter className="justify-start text-xs text-fg-muted">
                  {order.marking.next_attempt_at && (
                    <span>Следующая попытка: {formatDateTime(order.marking.next_attempt_at)} ·</span>
                  )}
                  Ключ идемпотентности{' '}
                  <span className="font-mono text-fg-label">{order.marking.idempotency_key.slice(0, 16)}…</span>
                </CardFooter>
              </Card>
            )}
          </div>
        </div>

        <Card>
          <CardHeader title="История изменений" />
          <CardBody>
            <Timeline events={history} />
          </CardBody>
        </Card>
      </div>
    </Page>
  )
}
