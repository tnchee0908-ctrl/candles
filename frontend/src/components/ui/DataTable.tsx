import type { HTMLAttributes, ReactNode, TdHTMLAttributes, ThHTMLAttributes } from 'react';
import { ArrowDown, ArrowUp } from 'lucide-react';
import { Link } from 'react-router-dom';
import { cn } from '@/lib/cn';

/**
 * Примитивы таблицы реестра. Строка 40 px, числа справа, единицы приглушены.
 * Компонуются вручную — так проще держать фильтры и колонки под конкретный экран.
 *
 *  <TableScroll>
 *    <Table minWidth={1100} fixed>
 *      <thead>
 *        <tr><Th sortable sort="desc" onSort={…}>Дата</Th>…</tr>
 *        <FilterRow>…</FilterRow>
 *      </thead>
 *      <tbody><Tr>…</Tr></tbody>
 *    </Table>
 *  </TableScroll>
 */

export function TableScroll({ className, ...rest }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn('overflow-x-auto', className)} {...rest} />;
}

interface TableProps extends HTMLAttributes<HTMLTableElement> {
  /** Минимальная ширина — ниже неё таблица скроллится внутри карточки */
  minWidth?: number;
  /** table-layout: fixed + <colgroup> для широких реестров */
  fixed?: boolean;
}

export function Table({ minWidth, fixed, className, style, ...rest }: TableProps) {
  return (
    <table
      className={cn('w-full border-separate border-spacing-0 tabular-nums', fixed && 'table-fixed', className)}
      style={{ minWidth, ...style }}
      {...rest}
    />
  );
}

export type SortDir = 'asc' | 'desc' | null;
type Align = 'left' | 'right' | 'center';

interface ThProps extends ThHTMLAttributes<HTMLTableCellElement> {
  align?: Align;
  sortable?: boolean;
  sort?: SortDir;
  onSort?: () => void;
}

export function Th({ align = 'left', sortable, sort, onSort, className, children, ...rest }: ThProps) {
  const active = Boolean(sort);
  const content = (
    <>
      {children}
      {sort === 'asc' && <ArrowUp className="ml-0.5 inline size-3.5 align-[-3px] text-accent" aria-hidden />}
      {sort === 'desc' && <ArrowDown className="ml-0.5 inline size-3.5 align-[-3px] text-accent" aria-hidden />}
    </>
  );
  return (
    <th
      aria-sort={sort === 'asc' ? 'ascending' : sort === 'desc' ? 'descending' : undefined}
      className={cn(
        'h-9 whitespace-nowrap border-b border-border bg-subtle px-2.5 text-xs font-medium first:pl-4 last:pr-4',
        active ? 'text-fg' : 'text-fg-muted',
        align === 'left' && 'text-left',
        align === 'right' && 'text-right',
        align === 'center' && 'text-center',
        className,
      )}
      {...rest}
    >
      {sortable ? (
        <button
          type="button"
          onClick={onSort}
          className="inline-flex items-center rounded-sm hover:text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/30"
        >
          {content}
        </button>
      ) : (
        content
      )}
    </th>
  );
}

/** Строка фильтров под заголовками */
export function FilterRow({ children }: { children: ReactNode }) {
  return <tr className="[&>td]:h-11 [&>td]:border-b [&>td]:border-border [&>td]:bg-subtle [&>td]:px-1.5 [&>td:first-child]:pl-2.5 [&>td:last-child]:pr-2.5">{children}</tr>;
}

interface TrProps extends HTMLAttributes<HTMLTableRowElement> {
  /** Подсветка строки с проблемой (дефицит) */
  highlight?: boolean;
}

export function Tr({ highlight, className, ...rest }: TrProps) {
  return (
    <tr
      className={cn(
        '[&>td]:transition-colors hover:[&>td]:bg-subtle [&:last-child>td]:border-b-0',
        highlight && '[&>td]:bg-highlight',
        className,
      )}
      {...rest}
    />
  );
}

interface TdProps extends TdHTMLAttributes<HTMLTableCellElement> {
  align?: Align;
  truncate?: boolean;
  /** Разрешить перенос (журнал изменений) */
  wrap?: boolean;
  muted?: boolean;
}

export function Td({ align = 'left', truncate, wrap, muted, className, ...rest }: TdProps) {
  return (
    <td
      className={cn(
        'h-row border-b border-border-soft px-2.5 first:pl-4 last:pr-4',
        wrap ? 'whitespace-normal py-2.5 align-top' : 'whitespace-nowrap',
        truncate && 'overflow-hidden text-ellipsis',
        align === 'right' && 'text-right',
        align === 'center' && 'text-center',
        muted && 'text-fg-muted',
        className,
      )}
      {...rest}
    />
  );
}

/** «—» для пустого значения */
export function Dash() {
  return <span className="text-fg-subtle">—</span>;
}

/** Номер документа — ссылка: П-00014, З-00016 */
export function DocLink({ to, children }: { to: string; children: ReactNode }) {
  return (
    <Link to={to} className="font-medium text-accent hover:text-accent-ink hover:underline">
      {children}
    </Link>
  );
}
