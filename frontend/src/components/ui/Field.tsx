import {
  forwardRef,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
} from 'react';
import { AlertCircle, ChevronDown } from 'lucide-react';
import { cn } from '@/lib/cn';

/* ---------- Field: метка + контрол + подсказка/ошибка ---------- */

interface FieldProps {
  label?: ReactNode;
  htmlFor?: string;
  hint?: ReactNode;
  error?: ReactNode;
  required?: boolean;
  className?: string;
  children: ReactNode;
}

export function Field({ label, htmlFor, hint, error, required, className, children }: FieldProps) {
  return (
    <div className={cn('flex min-w-0 flex-col gap-1.5', className)}>
      {label && (
        <label htmlFor={htmlFor} className="text-sm font-medium text-fg-label">
          {label}
          {required && <span className="ml-0.5 text-danger-fg">*</span>}
        </label>
      )}
      {children}
      {error ? (
        <span className="flex items-center gap-1 text-xs text-danger-fg" role="alert">
          <AlertCircle className="size-3" aria-hidden />
          {error}
        </span>
      ) : hint ? (
        <span className="text-xs text-fg-muted">{hint}</span>
      ) : null}
    </div>
  );
}

/* ---------- общий стиль контролов ---------- */

export type ControlSize = 'sm' | 'md';

export const controlClass = (size: ControlSize = 'md', invalid?: boolean) =>
  cn(
    'w-full min-w-0 rounded border bg-surface text-fg placeholder:text-fg-faint transition-[border-color,box-shadow]',
    'hover:border-border-hover focus:outline-none focus:ring-[3px]',
    'disabled:border-border disabled:bg-canvas disabled:text-fg-faint',
    invalid
      ? 'border-danger-dot focus:border-danger-dot focus:ring-danger-dot/15'
      : 'border-border-strong focus:border-accent focus:ring-accent/20',
    size === 'md' ? 'h-control px-2.5 text-base' : 'h-control-sm px-2 text-sm',
  );

/* ---------- Input ---------- */

export interface InputProps extends Omit<InputHTMLAttributes<HTMLInputElement>, 'size'> {
  size?: ControlSize;
  invalid?: boolean;
  /** Иконка слева (Search, Calendar…) */
  leftIcon?: ReactNode;
  /** Иконка справа */
  rightIcon?: ReactNode;
  /** Текстовый суффикс внутри поля: «кг», «EUR» */
  suffix?: ReactNode;
  /** Числовое поле: выравнивание вправо, табличные цифры */
  numeric?: boolean;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(function Input(
  { size = 'md', invalid, leftIcon, rightIcon, suffix, numeric, className, ...rest },
  ref,
) {
  const sm = size === 'sm';
  return (
    <span className="relative block min-w-0">
      {leftIcon && (
        <span
          className={cn(
            'pointer-events-none absolute top-1/2 -translate-y-1/2 text-fg-subtle',
            sm ? 'left-2 [&_svg]:size-3.5' : 'left-2.5 [&_svg]:size-4',
          )}
        >
          {leftIcon}
        </span>
      )}
      <input
        ref={ref}
        aria-invalid={invalid || undefined}
        inputMode={numeric ? 'decimal' : undefined}
        className={cn(
          controlClass(size, invalid),
          numeric && 'text-right tabular-nums',
          leftIcon && (sm ? 'pl-7' : 'pl-8'),
          (rightIcon || suffix) && 'pr-11',
          className,
        )}
        {...rest}
      />
      {(rightIcon || suffix) && (
        <span
          className={cn(
            'pointer-events-none absolute top-1/2 -translate-y-1/2 text-sm text-fg-subtle',
            sm ? 'right-2 [&_svg]:size-3.5' : 'right-2.5 [&_svg]:size-4',
          )}
        >
          {suffix ?? rightIcon}
        </span>
      )}
    </span>
  );
});

/* ---------- Select ---------- */

export interface SelectProps extends Omit<SelectHTMLAttributes<HTMLSelectElement>, 'size'> {
  size?: ControlSize;
  invalid?: boolean;
}

export const Select = forwardRef<HTMLSelectElement, SelectProps>(function Select(
  { size = 'md', invalid, className, children, ...rest },
  ref,
) {
  return (
    <span className="relative block min-w-0">
      <select
        ref={ref}
        aria-invalid={invalid || undefined}
        className={cn(controlClass(size, invalid), 'cursor-pointer appearance-none pr-8', className)}
        {...rest}
      >
        {children}
      </select>
      <ChevronDown
        aria-hidden
        className={cn(
          'pointer-events-none absolute top-1/2 -translate-y-1/2 text-fg-muted',
          size === 'sm' ? 'right-2 size-3.5' : 'right-2.5 size-4',
        )}
      />
    </span>
  );
});

/* ---------- Textarea ---------- */

export interface TextareaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  invalid?: boolean;
}

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(function Textarea(
  { invalid, className, rows = 3, ...rest },
  ref,
) {
  return (
    <textarea
      ref={ref}
      rows={rows}
      aria-invalid={invalid || undefined}
      className={cn(controlClass('md', invalid), 'h-auto min-h-[76px] resize-y py-2', className)}
      {...rest}
    />
  );
});
