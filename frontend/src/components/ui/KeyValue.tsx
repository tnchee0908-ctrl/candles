import type { ReactNode } from 'react';
import { cn } from '@/lib/cn';

export interface KeyValueItem {
  label: ReactNode;
  value: ReactNode;
  /** Выделить значение (например, «Свободно») */
  emphasis?: boolean;
  /** Пояснение под значением */
  note?: ReactNode;
}

/** Список «ключ — значение» для карточек партии и задания. */
export function KeyValueList({ items, className }: { items: KeyValueItem[]; className?: string }) {
  return (
    <dl className={cn('grid grid-cols-[150px_minmax(0,1fr)]', className)}>
      {items.map((item, i) => {
        const last = i === items.length - 1;
        return (
          <div key={i} className="contents">
            <dt className={cn('py-2 text-fg-muted', !last && 'border-b border-border-soft')}>{item.label}</dt>
            <dd className={cn('py-2 tabular-nums', !last && 'border-b border-border-soft', item.emphasis && 'font-semibold')}>
              {item.value}
              {item.note && <div className="mt-1 text-xs font-normal text-warning-fg">{item.note}</div>}
            </dd>
          </div>
        );
      })}
    </dl>
  );
}

/** Число с приглушённой единицей измерения: 30 кг */
export function Qty({ value, unit, className }: { value: ReactNode; unit?: ReactNode; className?: string }) {
  return (
    <span className={cn('tabular-nums', className)}>
      {value}
      {unit && <span className="font-normal text-fg-subtle"> {unit}</span>}
    </span>
  );
}

/** Код материала моноширинным: WAX-SOY */
export function MaterialCode({ children }: { children: ReactNode }) {
  return <span className="ml-1.5 font-mono text-[11.5px] text-fg-subtle">{children}</span>;
}
