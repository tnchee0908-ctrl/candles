import { Check, CircleX, Package } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { api } from '@/api'
import { useAuth } from '@/auth'
import { Page } from '@/components/layout/AppShell'
import {
  Banner,
  BatchStatusBadge,
  Button,
  Card,
  CardBody,
  CardHeader,
  CardSkeleton,
  DocLink,
  EmptyState,
  KeyValueList,
  MaterialCode,
  PageHeader,
  Qty,
  Table,
  Td,
  Timeline,
  Tr,
} from '@/components/ui'
import { auditToEvent } from '@/lib/audit'
import { formatDate, formatDateTime, formatMoney, formatQty, type Currency } from '@/lib/format'
import type { BatchCard, Movement } from '@/types'

/** 04–05 — Карточка партии. Кладовщику и руководителю у партии на проверке — «Принять» и «Брак». */
export default function BatchCardPage() {
  const { id } = useParams()
  const { can } = useAuth()
  const [card, setCard] = useState<BatchCard | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState<'accepted' | 'rejected' | null>(null)

  const load = useCallback(() => {
    api<BatchCard>(`/api/batches/${id}`)
      .then(setCard)
      .catch((e) => setError(e.message))
  }, [id])
  useEffect(load, [load])

  async function setStatus(status: 'accepted' | 'rejected') {
    setBusy(status)
    setError(null)
    try {
      await api(`/api/batches/${id}/status`, { method: 'POST', json: { status } })
      load()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(null)
    }
  }

  if (!card) {
    return <Page>{error ? <Banner tone="error">{error}</Banner> : <CardSkeleton lines={6} />}</Page>
  }

  const b = card.batch
  const foreign = b.currency !== 'RUB'
  const weekendRate = foreign && b.rate_date !== b.received_date
  const canCheck = b.status === 'on_check' && can('set_batch_status')
  const history = card.history.map((e) => auditToEvent(e, { unit: b.unit, currency: b.currency as Currency }))

  return (
    <Page>
      <PageHeader
        breadcrumbs={[{ label: 'Реестр партий', to: '/batches' }, { label: b.number }]}
        title={`Партия ${b.number}`}
        badge={<BatchStatusBadge status={b.status} />}
        subtitle={
          <>
            {b.material}
            <MaterialCode>{b.material_code}</MaterialCode> · поступление {card.receipt_number} от{' '}
            {formatDate(b.received_date)} · {b.supplier}
          </>
        }
        actions={
          canCheck && (
            <>
              <Button
                variant="danger"
                icon={<CircleX />}
                loading={busy === 'rejected'}
                disabled={busy !== null}
                onClick={() => setStatus('rejected')}
              >
                Брак
              </Button>
              <Button
                variant="primary"
                icon={<Check />}
                loading={busy === 'accepted'}
                disabled={busy !== null}
                onClick={() => setStatus('accepted')}
              >
                Принять
              </Button>
            </>
          )
        }
      />

      <div className="flex flex-col gap-4">
        {error && <Banner tone="error">{error}</Banner>}
        {b.status === 'on_check' && (
          <Banner tone="warning">
            Партия ждёт проверки качества. Пока она не принята, материал нельзя резервировать:{' '}
            {formatQty(b.qty)} {b.unit} учитываются в остатках как «Ждёт приёмки».
          </Banner>
        )}

        <div className="grid grid-cols-[repeat(auto-fit,minmax(min(100%,420px),1fr))] gap-4">
          <Card>
            <CardHeader title="Сведения" />
            <CardBody className="pb-3 pt-1">
              <KeyValueList
                items={[
                  { label: 'Пришло', value: <Qty value={formatQty(b.qty)} unit={b.unit} /> },
                  { label: 'Остаток', value: <Qty value={formatQty(b.remaining_qty)} unit={b.unit} /> },
                  { label: 'В резерве', value: <Qty value={formatQty(b.reserved_qty)} unit={b.unit} /> },
                  { label: 'Свободно', value: <Qty value={formatQty(b.free_qty)} unit={b.unit} />, emphasis: true },
                  {
                    label: 'Цена',
                    value: (
                      <>
                        {formatMoney(b.price, b.currency as Currency)}{' '}
                        <span className="text-fg-subtle">за {b.unit}</span>
                      </>
                    ),
                  },
                  {
                    label: 'Курс',
                    value: foreign ? (
                      <>
                        {formatQty(b.rate)} ₽ за 1 {b.currency}{' '}
                        <span className="text-fg-subtle">· на {formatDate(b.rate_date)}</span>
                      </>
                    ) : (
                      <span className="text-fg-subtle">не требуется — рубли</span>
                    ),
                    note: weekendRate ? 'Поставка в нерабочий день — взят последний курс' : undefined,
                  },
                  {
                    label: 'Себестоимость',
                    value: (
                      <>
                        {formatMoney(b.unit_cost_rub)} <span className="font-normal text-fg-subtle">за {b.unit}</span>
                      </>
                    ),
                    emphasis: true,
                  },
                ]}
              />
              {b.comment && (
                <div className="mt-3 rounded border border-border-soft bg-subtle px-3 py-2.5">
                  <div className="mb-0.5 text-2xs font-medium uppercase tracking-[0.06em] text-fg-muted">
                    Комментарий
                  </div>
                  {b.comment}
                </div>
              )}
            </CardBody>
          </Card>

          <Card>
            <CardHeader title="Движения" />
            {card.reservations.length + card.consumptions.length === 0 ? (
              <EmptyState
                icon={<Package />}
                title="Резервов и списаний нет"
                description="Они появятся, когда партию примут и задания начнут брать из неё материал."
                className="pt-12"
              />
            ) : (
              <CardBody className="flex flex-col gap-5">
                <MovementList title="Резервы" rows={card.reservations} unit={b.unit} />
                <MovementList title="Списания" rows={card.consumptions} unit={b.unit} withDate />
              </CardBody>
            )}
          </Card>
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

function MovementList({
  title,
  rows,
  unit,
  withDate,
}: {
  title: string
  rows: Movement[]
  unit: string
  withDate?: boolean
}) {
  if (!rows.length) return null
  const total = rows.reduce((s, r) => s + Number(r.qty), 0)
  return (
    <div>
      <div className="mb-1.5 flex justify-between">
        <span className="text-2xs font-medium uppercase tracking-[0.06em] text-fg-muted">{title}</span>
        <span className="text-xs tabular-nums text-fg-muted">
          {formatQty(total)} {unit}
        </span>
      </div>
      <Table>
        <tbody>
          {rows.map((r, i) => (
            <Tr key={`${r.order_id}-${i}`}>
              <Td className="!pl-0">
                <DocLink to={`/orders/${r.order_id}`}>{r.order_number}</DocLink>
                {withDate && r.at && <span className="text-fg-muted"> · {formatDateTime(r.at)}</span>}
              </Td>
              <Td align="right" className="!pr-0">
                <Qty value={formatQty(r.qty)} unit={unit} />
              </Td>
            </Tr>
          ))}
        </tbody>
      </Table>
    </div>
  )
}
