import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from 'react';
import { Loader2 } from 'lucide-react';
import { cn } from '@/lib/cn';
import { Tooltip } from './Tooltip';

export type ButtonVariant = 'primary' | 'secondary' | 'danger' | 'ghost';
export type ButtonSize = 'sm' | 'md';

const base =
  'inline-flex items-center justify-center whitespace-nowrap rounded border font-medium transition-colors ' +
  'focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-accent/30 ' +
  'disabled:cursor-not-allowed disabled:border-border disabled:bg-muted disabled:text-fg-faint';

const variants: Record<ButtonVariant, string> = {
  primary: 'border-transparent bg-accent text-white hover:bg-accent-hover',
  secondary: 'border-border-strong bg-surface text-fg hover:border-border-hover hover:bg-canvas',
  danger: 'border-danger-border bg-surface text-danger-fg hover:bg-danger-bg',
  ghost: 'border-transparent bg-transparent text-fg-label hover:bg-hover hover:text-fg disabled:border-transparent disabled:bg-transparent',
};

const sizes: Record<ButtonSize, string> = {
  md: 'h-control gap-1.5 px-3.5 text-base [&_svg]:size-4',
  sm: 'h-control-sm gap-[5px] px-2.5 text-sm [&_svg]:size-3.5',
};

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  /** Иконка lucide слева от текста */
  icon?: ReactNode;
  /** Иконка справа (например, ChevronDown) */
  iconRight?: ReactNode;
  loading?: boolean;
  /** Причина недоступности — показывается тултипом, кнопка становится disabled */
  disabledReason?: string;
  fullWidth?: boolean;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  {
    variant = 'secondary',
    size = 'md',
    icon,
    iconRight,
    loading,
    disabledReason,
    disabled,
    fullWidth,
    className,
    children,
    type = 'button',
    ...rest
  },
  ref,
) {
  const isDisabled = disabled || loading || Boolean(disabledReason);
  const button = (
    <button
      ref={ref}
      type={type}
      disabled={isDisabled}
      aria-busy={loading || undefined}
      className={cn(base, variants[variant], sizes[size], fullWidth && 'w-full', className)}
      {...rest}
    >
      {loading ? <Loader2 className="animate-spin" aria-hidden /> : icon}
      {children}
      {!loading && iconRight}
    </button>
  );

  if (disabledReason) return <Tooltip content={disabledReason}>{button}</Tooltip>;
  return button;
});

/** Квадратная кнопка с иконкой. Подпись обязательна — для скринридеров и тултипа. */
export interface IconButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  label: string;
  size?: ButtonSize;
  tone?: 'default' | 'danger';
  children: ReactNode;
}

export const IconButton = forwardRef<HTMLButtonElement, IconButtonProps>(function IconButton(
  { label, size = 'md', tone = 'default', className, children, type = 'button', ...rest },
  ref,
) {
  return (
    <button
      ref={ref}
      type={type}
      aria-label={label}
      title={label}
      className={cn(
        'inline-flex shrink-0 items-center justify-center rounded text-fg-muted transition-colors',
        'focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-accent/30',
        'disabled:cursor-not-allowed disabled:text-border-hover disabled:hover:bg-transparent',
        size === 'md' ? 'size-8 [&_svg]:size-4' : 'size-7 [&_svg]:size-4',
        tone === 'danger' ? 'hover:bg-danger-bg hover:text-danger-fg' : 'hover:bg-muted hover:text-fg',
        className,
      )}
      {...rest}
    >
      {children}
    </button>
  );
});
