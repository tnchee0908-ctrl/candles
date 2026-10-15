import type { ReactNode } from 'react';
import { Loader2 } from 'lucide-react';
import { cn } from '@/lib/cn';

export type Tone = 'success' | 'warning' | 'danger' | 'info' | 'progress' | 'neutral';

const toneClass: Record<Tone, { box: string; dot: string }> = {
  success: { box: 'bg-success-bg text-success-fg', dot: 'bg-success-dot' },
  warning: { box: 'bg-warning-bg text-warning-fg', dot: 'bg-warning-dot' },
  danger: { box: 'bg-danger-bg text-danger-fg', dot: 'bg-danger-dot' },
  info: { box: 'bg-info-bg text-info-fg', dot: 'bg-info-dot' },
  progress: { box: 'bg-progress-bg text-progress-fg', dot: 'bg-progress-dot' },
  neutral: { box: 'bg-neutral-bg text-neutral-fg', dot: 'bg-neutral-dot' },
};

interface BadgeProps {
  tone: Tone;
  children: ReactNode;
  /** Вместо точки — индикатор загрузки (для «Отправляется») */
  loading?: boolean;
  className?: string;
}

/** Бейдж статуса: приглушённый фон, насыщенный текст и точка. */
export function Badge({ tone, children, loading, className }: BadgeProps) {
  const t = toneClass[tone];
  return (
    <span
      className={cn(
        'inline-flex h-[22px] items-center gap-1.5 whitespace-nowrap rounded-sm px-2 text-xs font-medium',
        t.box,
        className,
      )}
    >
      {loading ? (
        <Loader2 className="size-3 animate-spin" aria-hidden />
      ) : (
        <span className={cn('size-1.5 shrink-0 rounded-full', t.dot)} aria-hidden />
      )}
      {children}
    </span>
  );
}

/* ---------- статусы предметной области ---------- */

export type BatchStatus = 'on_check' | 'accepted' | 'rejected';
export type OrderStatus = 'draft' | 'planned' | 'in_progress' | 'completed' | 'cancelled';
export type MarkingStatus = 'sent' | 'sending' | 'failed';

export const BATCH_STATUS: Record<BatchStatus, [string, Tone]> = {
  on_check: ['На проверке', 'warning'],
  accepted: ['Принята', 'success'],
  rejected: ['Брак', 'danger'],
};

export const ORDER_STATUS: Record<OrderStatus, [string, Tone]> = {
  draft: ['Черновик', 'neutral'],
  planned: ['Запланировано', 'info'],
  in_progress: ['В работе', 'progress'],
  completed: ['Завершено', 'success'],
  cancelled: ['Отменено', 'neutral'],
};

export const MARKING_STATUS: Record<MarkingStatus, [string, Tone]> = {
  sent: ['Отправлен', 'success'],
  sending: ['Отправляется', 'warning'],
  failed: ['Не отправлен', 'danger'],
};

export function BatchStatusBadge({ status }: { status: BatchStatus }) {
  const [label, tone] = BATCH_STATUS[status];
  return <Badge tone={tone}>{label}</Badge>;
}

export function OrderStatusBadge({ status }: { status: OrderStatus }) {
  const [label, tone] = ORDER_STATUS[status];
  return <Badge tone={tone}>{label}</Badge>;
}

export function MarkingStatusBadge({ status }: { status: MarkingStatus }) {
  const [label, tone] = MARKING_STATUS[status];
  return (
    <Badge tone={tone} loading={status === 'sending'}>
      {label}
    </Badge>
  );
}

/** Нейтральный тег: «через ассистента», «запасная модель», код материала. */
export function Tag({ children, mono, className }: { children: ReactNode; mono?: boolean; className?: string }) {
  return (
    <span
      className={cn(
        'inline-flex h-5 items-center gap-1 whitespace-nowrap rounded-sm border border-border bg-surface px-1.5 text-2xs font-medium text-fg-secondary [&_svg]:size-3',
        mono && 'font-mono',
        className,
      )}
    >
      {children}
    </span>
  );
}
