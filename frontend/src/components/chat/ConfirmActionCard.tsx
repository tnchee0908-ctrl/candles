import type { ReactNode } from 'react';
import { Ban, CircleCheck, CircleX, ClipboardCheck, TriangleAlert } from 'lucide-react';
import { Link } from 'react-router-dom';
import { formatQty } from '@/lib/format';
import { Button, Dash, ReserveDot, Table, Td, Th, Tr } from '@/components/ui';
import type { ConfirmAction } from './types';

interface ConfirmActionCardProps {
  action: ConfirmAction;
  onConfirm: () => void;
  onReject: () => void;
}

/**
 * Ключевой элемент продукта: ассистент предлагает действие, данные меняются
 * только после «Подтвердить». Выделяется спокойно — тёплый фон и рамка акцента.
 */
export function ConfirmActionCard({ action, onConfirm, onReject }: ConfirmActionCardProps) {
  const { state } = action;

  if (state.kind === 'confirmed') {
    return (
      <ResultCard tone="success" icon={<CircleCheck />} title={`Подтверждено · ${state.at}`}>
        Создано задание{' '}
        <Link to={state.orderUrl} className="font-medium text-accent hover:underline">
          {state.orderNo}
        </Link>
        .{state.deficitNote && <div className="mt-0.5 text-sm text-fg-muted">{state.deficitNote}</div>}
      </ResultCard>
    );
  }
  if (state.kind === 'rejected') {
    return (
      <ResultCard tone="neutral" icon={<Ban />} title="Отклонено">
        <span className="text-fg-muted">Действие не выполнено, данные не изменились.</span>
      </ResultCard>
    );
  }
  if (state.kind === 'failed') {
    return (
      <ResultCard tone="danger" icon={<CircleX />} title="Не выполнено">
        <span className="text-danger-ink">{state.error}</span>
      </ResultCard>
    );
  }

  const submitting = state.kind === 'submitting';
  return (
    <section role="group" aria-labelledby={`${action.id}-title`} className="rounded-lg border border-accent-200 bg-accent-25 p-4">
      <div className="flex items-center gap-2 text-xs font-semibold tracking-[0.02em] text-accent-hover">
        <ClipboardCheck className="size-3.5" aria-hidden />
        Требуется подтверждение
      </div>
      <div id={`${action.id}-title`} className="mt-1.5 font-semibold">
        {action.title}
      </div>

      <div className="mt-3 overflow-hidden rounded-lg border border-border bg-surface">
        <Table>
          <thead>
            <tr>
              <Th className="w-10">
                <span className="sr-only">Резерв</span>
              </Th>
              <Th>Материал</Th>
              <Th align="right">Нужно</Th>
              <Th align="right">Свободно</Th>
              <Th align="right">Дефицит</Th>
            </tr>
          </thead>
          <tbody>
            {action.rows.map((r) => (
              <Tr key={r.material}>
                <Td>
                  <ReserveDot level={r.level} />
                </Td>
                <Td>{r.material}</Td>
                <Td align="right">
                  {formatQty(r.need)} <span className="text-fg-subtle">{r.unit}</span>
                </Td>
                <Td align="right">{formatQty(r.free)}</Td>
                <Td align="right">
                  {r.deficit ? (
                    <span className="font-semibold text-danger-fg">
                      {formatQty(r.deficit)} <span className="font-normal">{r.unit}</span>
                    </span>
                  ) : (
                    <Dash />
                  )}
                </Td>
              </Tr>
            ))}
          </tbody>
        </Table>
      </div>

      {action.warning && (
        <p className="mt-2.5 flex items-start gap-2 text-sm text-warning-fg">
          <TriangleAlert className="mt-0.5 size-3.5 shrink-0 text-warning-icon" aria-hidden />
          {action.warning}
        </p>
      )}

      <div className="mt-3.5 flex flex-wrap items-center gap-2">
        <Button variant="primary" onClick={onConfirm} loading={submitting}>
          Подтвердить
        </Button>
        <Button variant="secondary" onClick={onReject} disabled={submitting}>
          Отклонить
        </Button>
        <span className="ml-1 text-xs text-fg-muted">До нажатия ничего не изменится</span>
      </div>
    </section>
  );
}

function ResultCard({
  tone,
  icon,
  title,
  children,
}: {
  tone: 'success' | 'neutral' | 'danger';
  icon: ReactNode;
  title: string;
  children: ReactNode;
}) {
  const border = tone === 'success' ? 'border-success-border' : tone === 'danger' ? 'border-danger-border' : 'border-border';
  const color = tone === 'success' ? 'text-success-fg' : tone === 'danger' ? 'text-danger-fg' : 'text-fg-secondary';
  return (
    <section className={`rounded-lg border bg-surface px-4 py-3.5 ${border}`} role="status">
      <div className={`flex items-center gap-2 text-xs font-semibold [&_svg]:size-3.5 ${color}`}>
        {icon}
        {title}
      </div>
      <div className="mt-1.5">{children}</div>
    </section>
  );
}
