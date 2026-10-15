import type { ReactNode } from 'react';
import { CircleCheck, CircleX, Info, TriangleAlert, X } from 'lucide-react';
import { cn } from '@/lib/cn';
import { IconButton } from './Button';

export type BannerTone = 'error' | 'success' | 'warning' | 'info';

const tones: Record<BannerTone, { box: string; icon: string; Icon: typeof Info; role: 'alert' | 'status' }> = {
  error: { box: 'border-danger-border bg-danger-bg/70 text-danger-ink', icon: 'text-danger-dot', Icon: CircleX, role: 'alert' },
  success: { box: 'border-success-border bg-success-bg/70 text-success-fg', icon: 'text-success-dot', Icon: CircleCheck, role: 'status' },
  warning: { box: 'border-warning-border bg-warning-bg/60 text-warning-fg', icon: 'text-warning-icon', Icon: TriangleAlert, role: 'status' },
  info: { box: 'border-border bg-subtle text-fg-label', icon: 'text-fg-muted', Icon: Info, role: 'status' },
};

interface BannerProps {
  tone: BannerTone;
  /** Короткая жирная фраза перед текстом */
  title?: ReactNode;
  /** Текст — как пришёл с сервера, человеческим языком */
  children: ReactNode;
  onDismiss?: () => void;
  className?: string;
}

export function Banner({ tone, title, children, onDismiss, className }: BannerProps) {
  const t = tones[tone];
  return (
    <div role={t.role} className={cn('flex items-start gap-2.5 rounded border py-2.5 pl-3.5 pr-3', t.box, className)}>
      <t.Icon className={cn('mt-0.5 size-4 shrink-0', t.icon)} aria-hidden />
      <div className="min-w-0 flex-1">
        {title && <strong className="font-semibold">{title} </strong>}
        {children}
      </div>
      {onDismiss && (
        <IconButton label="Скрыть" size="sm" onClick={onDismiss} className="-my-1 -mr-1">
          <X />
        </IconButton>
      )}
    </div>
  );
}
