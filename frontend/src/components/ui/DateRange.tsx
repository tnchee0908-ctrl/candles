import { useEffect, useRef, useState } from 'react';
import { Calendar, X } from 'lucide-react';
import { cn } from '@/lib/cn';
import { formatDate } from '@/lib/format';
import { Button } from './Button';
import { Field, Input, controlClass, type ControlSize } from './Field';

interface DateRangeProps {
  from: string;
  to: string;
  onChange: (from: string, to: string) => void;
  size?: ControlSize;
  placeholder?: string;
  label: string;
}

/** Фильтр «период»: кнопка-поле с выбранным диапазоном, по клику — две даты во всплывающей панели. */
export function DateRange({ from, to, onChange, size = 'md', placeholder = 'Период', label }: DateRangeProps) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => {
      if (box.current && !box.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', close);
    return () => document.removeEventListener('mousedown', close);
  }, [open]);

  const text = from || to ? `${from ? formatDate(from) : '…'} – ${to ? formatDate(to) : '…'}` : '';

  return (
    <div ref={box} className="relative">
      <button
        type="button"
        aria-label={label}
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        className={cn(controlClass(size), 'flex items-center justify-between gap-1 text-left')}
      >
        <span className={cn('truncate', !text && 'text-fg-faint')}>{text || placeholder}</span>
        <Calendar className="size-3.5 shrink-0 text-fg-subtle" aria-hidden />
      </button>
      {open && (
        <div className="absolute left-0 top-[calc(100%+4px)] z-30 flex w-[260px] flex-col gap-3 rounded-lg border border-border bg-surface p-3 font-normal shadow-popover">
          <div className="grid grid-cols-2 gap-2">
            <Field label="С">
              <Input size="sm" type="date" value={from} max={to || undefined} onChange={(e) => onChange(e.target.value, to)} />
            </Field>
            <Field label="По">
              <Input size="sm" type="date" value={to} min={from || undefined} onChange={(e) => onChange(from, e.target.value)} />
            </Field>
          </div>
          <div className="flex justify-between">
            <Button size="sm" variant="ghost" icon={<X />} disabled={!from && !to} onClick={() => onChange('', '')}>
              Сбросить
            </Button>
            <Button size="sm" onClick={() => setOpen(false)}>
              Готово
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
