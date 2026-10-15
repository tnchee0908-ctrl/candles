import { ChevronLeft, ChevronRight } from 'lucide-react';
import { IconButton } from './Button';
import { Select } from './Field';

interface PaginationProps {
  total: number;
  page: number; // с 1
  pageSize: number;
  onPage: (page: number) => void;
  onPageSize?: (size: number) => void;
  pageSizes?: number[];
  totalLabel?: string;
}

export function Pagination({
  total,
  page,
  pageSize,
  onPage,
  onPageSize,
  pageSizes = [20, 50, 100],
  totalLabel = 'Всего',
}: PaginationProps) {
  const pageCount = Math.max(1, Math.ceil(total / pageSize));
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border py-2.5 pl-4 pr-3 text-sm text-fg-secondary">
      <span>
        {totalLabel}: <b className="font-semibold text-fg">{total}</b>
      </span>
      <div className="flex items-center gap-2">
        {onPageSize && (
          <div className="w-[92px]">
            <Select size="sm" value={pageSize} onChange={(e) => onPageSize(Number(e.target.value))} aria-label="Строк на странице">
              {pageSizes.map((s) => (
                <option key={s} value={s}>
                  по {s}
                </option>
              ))}
            </Select>
          </div>
        )}
        <IconButton label="Предыдущая страница" size="sm" disabled={page <= 1} onClick={() => onPage(page - 1)}>
          <ChevronLeft />
        </IconButton>
        <span className="tabular-nums">
          {page} из {pageCount}
        </span>
        <IconButton label="Следующая страница" size="sm" disabled={page >= pageCount} onClick={() => onPage(page + 1)}>
          <ChevronRight />
        </IconButton>
      </div>
    </div>
  );
}
