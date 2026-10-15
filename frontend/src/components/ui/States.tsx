import type { ReactNode } from 'react';
import { cn } from '@/lib/cn';

/* ---------- Пустое состояние: иконка, короткий текст, действие ---------- */

interface EmptyStateProps {
  icon: ReactNode;
  title: ReactNode;
  description?: ReactNode;
  action?: ReactNode;
  className?: string;
}

export function EmptyState({ icon, title, description, action, className }: EmptyStateProps) {
  return (
    <div className={cn('flex flex-col items-center gap-1.5 px-4 py-7 text-center text-fg-secondary', className)}>
      <div className="mb-1 flex size-9 items-center justify-center rounded-lg bg-[#F4F2EF] text-fg-muted [&_svg]:size-[18px]">
        {icon}
      </div>
      <div className="font-semibold text-fg">{title}</div>
      {description && <div className="max-w-[300px] text-sm">{description}</div>}
      {action && <div className="mt-1.5">{action}</div>}
    </div>
  );
}

/* ---------- Скелетоны ---------- */

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn('h-3 animate-pulse rounded-sm bg-hover', className)} aria-hidden />;
}

export function TableSkeleton({ rows = 6, cols = 5 }: { rows?: number; cols?: number }) {
  return (
    <div className="divide-y divide-[#F1EFEC]" aria-busy="true" aria-label="Загрузка">
      {Array.from({ length: rows }).map((_, r) => (
        <div key={r} className="flex h-row items-center gap-4 px-4">
          {Array.from({ length: cols }).map((__, c) => (
            <Skeleton key={c} className={c === 1 ? 'flex-[2]' : 'flex-1'} />
          ))}
        </div>
      ))}
    </div>
  );
}

export function CardSkeleton({ lines = 4 }: { lines?: number }) {
  return (
    <div className="rounded-lg border border-border bg-surface" aria-busy="true" aria-label="Загрузка">
      <div className="border-b border-border-soft px-5 py-4">
        <Skeleton className="w-32" />
      </div>
      <div className="flex flex-col gap-4 px-5 py-4">
        {Array.from({ length: lines }).map((_, i) => (
          <div key={i} className="flex gap-4">
            <Skeleton className="w-24" />
            <Skeleton className="flex-1" />
          </div>
        ))}
      </div>
    </div>
  );
}

/* ---------- Segmented: быстрый фильтр по статусу ---------- */

interface SegmentedOption<T extends string> {
  value: T;
  label: ReactNode;
  count?: number;
}

interface SegmentedProps<T extends string> {
  options: SegmentedOption<T>[];
  value: T;
  onChange: (value: T) => void;
  label: string;
}

export function Segmented<T extends string>({ options, value, onChange, label }: SegmentedProps<T>) {
  return (
    <div role="tablist" aria-label={label} className="inline-flex gap-0.5 rounded bg-hover p-0.5">
      {options.map((o) => {
        const active = o.value === value;
        return (
          <button
            key={o.value}
            type="button"
            role="tab"
            aria-selected={active}
            onClick={() => onChange(o.value)}
            className={cn(
              'inline-flex h-7 items-center gap-1.5 rounded-sm px-2.5 text-sm font-medium transition-colors',
              'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/30',
              active ? 'bg-surface text-fg shadow-segment' : 'text-fg-secondary hover:text-fg',
            )}
          >
            {o.label}
            {o.count !== undefined && <span className="text-xs font-normal tabular-nums text-fg-muted">{o.count}</span>}
          </button>
        );
      })}
    </div>
  );
}
