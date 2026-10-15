import { useId, type ReactElement, type ReactNode } from 'react';
import { cn } from '@/lib/cn';

interface TooltipProps {
  content: ReactNode;
  children: ReactElement;
  side?: 'top' | 'bottom';
  align?: 'start' | 'center' | 'end';
}

/**
 * Лёгкий CSS-тултип: показывается при наведении и фокусе внутри обёртки.
 * Работает и для disabled-кнопок (события ловит обёртка, а не кнопка).
 */
export function Tooltip({ content, children, side = 'bottom', align = 'end' }: TooltipProps) {
  const id = useId();
  return (
    <span className="group/tip relative inline-flex" aria-describedby={id} tabIndex={-1}>
      {children}
      <span
        id={id}
        role="tooltip"
        className={cn(
          'pointer-events-none absolute z-50 whitespace-nowrap rounded bg-fg px-2 py-1.5 text-xs text-canvas shadow-tooltip',
          'opacity-0 transition-opacity duration-100 group-hover/tip:opacity-100 group-focus-within/tip:opacity-100',
          side === 'bottom' ? 'top-[calc(100%+6px)]' : 'bottom-[calc(100%+6px)]',
          align === 'end' && 'right-0',
          align === 'start' && 'left-0',
          align === 'center' && 'left-1/2 -translate-x-1/2',
        )}
      >
        {content}
      </span>
    </span>
  );
}
