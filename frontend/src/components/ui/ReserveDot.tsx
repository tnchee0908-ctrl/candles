import { cn } from '@/lib/cn';

/** Уровень резерва — «светофор». `none_draft` — черновик, резерв ещё не создавался. */
export type ReserveLevel = 'full' | 'partial' | 'none' | 'none_draft';

export const RESERVE_LABEL: Record<ReserveLevel, string> = {
  full: 'всё в резерве',
  partial: 'частично',
  none: 'ничего',
  none_draft: 'нет резерва',
};

const dotClass: Record<ReserveLevel, string> = {
  full: 'bg-success-dot',
  partial: 'bg-warning-dot',
  none: 'bg-danger-dot',
  none_draft: 'bg-border-strong',
};

interface ReserveDotProps {
  level: ReserveLevel;
  /** Показать подпись рядом; иначе подпись уходит в title и aria-label */
  showLabel?: boolean;
  className?: string;
}

export function ReserveDot({ level, showLabel, className }: ReserveDotProps) {
  const label = RESERVE_LABEL[level];
  return (
    <span
      className={cn('inline-flex items-center gap-2 whitespace-nowrap text-sm text-fg-secondary', className)}
      title={showLabel ? undefined : label}
      role={showLabel ? undefined : 'img'}
      aria-label={showLabel ? undefined : label}
    >
      <span className={cn('size-2 shrink-0 rounded-full', dotClass[level])} aria-hidden />
      {showLabel && label}
    </span>
  );
}

export function ReserveLegend({ className }: { className?: string }) {
  return (
    <div className={cn('flex flex-wrap gap-x-4 gap-y-1.5 text-xs text-fg-secondary', className)}>
      {(['full', 'partial', 'none'] as const).map((l) => (
        <span key={l} className="inline-flex items-center gap-1.5">
          <span className={cn('size-2 rounded-full', dotClass[l])} aria-hidden />
          {RESERVE_LABEL[l]}
        </span>
      ))}
    </div>
  );
}
