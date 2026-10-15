import type { HTMLAttributes, ReactNode } from 'react';
import { cn } from '@/lib/cn';

/** Карточка-секция: белая поверхность, тонкая граница, без тени. */
export function Card({ className, ...rest }: HTMLAttributes<HTMLElement>) {
  return <section className={cn('min-w-0 rounded-lg border border-border bg-surface', className)} {...rest} />;
}

interface CardHeaderProps {
  title: ReactNode;
  description?: ReactNode;
  /** Действия/легенда справа */
  actions?: ReactNode;
  className?: string;
}

export function CardHeader({ title, description, actions, className }: CardHeaderProps) {
  return (
    <header
      className={cn(
        'flex min-h-12 flex-wrap items-center justify-between gap-x-3 gap-y-2 border-b border-border-soft px-5 py-3',
        className,
      )}
    >
      <div className="min-w-0">
        <h2 className="text-base font-semibold">{title}</h2>
        {description && <p className="mt-0.5 text-sm text-fg-muted">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </header>
  );
}

export function CardBody({ className, ...rest }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn('px-5 py-4', className)} {...rest} />;
}

export function CardFooter({ className, ...rest }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn('flex flex-wrap items-center justify-between gap-3 border-t border-border-soft px-5 py-3', className)}
      {...rest}
    />
  );
}

/** Крупная метрика: итог себестоимости и т. п. */
export function Metric({ value, caption }: { value: ReactNode; caption?: ReactNode }) {
  return (
    <div>
      <div className="text-2xl font-semibold tabular-nums">{value}</div>
      {caption && <div className="mt-0.5 tabular-nums text-fg-secondary">{caption}</div>}
    </div>
  );
}
