import type { ButtonHTMLAttributes, ReactNode } from 'react'
import type { Light } from '../types'

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-2xl font-semibold text-stone-900">{title}</h1>
        {subtitle && <div className="mt-1 text-sm text-stone-500">{subtitle}</div>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </div>
  )
}

type Variant = 'primary' | 'secondary' | 'danger' | 'ghost'

const VARIANTS: Record<Variant, string> = {
  primary: 'bg-wax-600 text-white hover:bg-wax-700 disabled:bg-stone-300',
  secondary: 'bg-white text-stone-800 border border-stone-300 hover:bg-stone-50 disabled:text-stone-400',
  danger: 'bg-white text-red-700 border border-red-300 hover:bg-red-50 disabled:text-stone-400',
  ghost: 'text-stone-600 hover:bg-stone-100',
}

export function Button({
  variant = 'primary',
  className = '',
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant }) {
  return (
    <button
      className={`inline-flex items-center justify-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition disabled:cursor-not-allowed ${VARIANTS[variant]} ${className}`}
      {...props}
    />
  )
}

export function Card({ title, children, actions }: { title?: ReactNode; children: ReactNode; actions?: ReactNode }) {
  return (
    <section className="rounded-lg border border-stone-200 bg-white shadow-sm">
      {(title || actions) && (
        <div className="flex items-center justify-between border-b border-stone-100 px-4 py-2.5">
          <h2 className="text-sm font-semibold text-stone-800">{title}</h2>
          {actions}
        </div>
      )}
      <div className="p-4">{children}</div>
    </section>
  )
}

export function ErrorBox({ error }: { error: string | null }) {
  if (!error) return null
  return <div className="mb-4 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800">{error}</div>
}

export function Notice({ children }: { children: ReactNode }) {
  return <div className="mb-4 rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-800">{children}</div>
}

const LIGHT_STYLES: Record<Light, { dot: string; label: string }> = {
  green: { dot: 'bg-emerald-500', label: 'всё в резерве' },
  yellow: { dot: 'bg-amber-400', label: 'частично' },
  red: { dot: 'bg-red-500', label: 'ничего' },
}

export function LightDot({ light, withLabel = false }: { light: Light; withLabel?: boolean }) {
  const s = LIGHT_STYLES[light]
  return (
    <span className="inline-flex items-center gap-1.5" title={s.label}>
      <span className={`inline-block h-3 w-3 rounded-full ring-2 ring-white ${s.dot}`} />
      {withLabel && <span className="text-xs text-stone-600">{s.label}</span>}
    </span>
  )
}

const STATUS_COLORS: Record<string, string> = {
  on_check: 'bg-amber-100 text-amber-800',
  accepted: 'bg-emerald-100 text-emerald-800',
  rejected: 'bg-red-100 text-red-800',
  draft: 'bg-stone-100 text-stone-700',
  planned: 'bg-sky-100 text-sky-800',
  in_progress: 'bg-violet-100 text-violet-800',
  completed: 'bg-emerald-100 text-emerald-800',
  cancelled: 'bg-stone-200 text-stone-600',
  pending: 'bg-amber-100 text-amber-800',
  sent: 'bg-emerald-100 text-emerald-800',
  failed: 'bg-red-100 text-red-800',
}

export function StatusBadge({ status, title }: { status: string; title: string }) {
  return (
    <span className={`inline-block whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_COLORS[status] ?? 'bg-stone-100'}`}>
      {title}
    </span>
  )
}

export const inputCls =
  'w-full rounded-md border border-stone-300 bg-white px-2.5 py-1.5 text-sm focus:border-wax-500 focus:outline-none focus:ring-1 focus:ring-wax-500'

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-medium text-stone-600">{label}</span>
      {children}
    </label>
  )
}

export function Table({ children }: { children: ReactNode }) {
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full text-sm">{children}</table>
    </div>
  )
}

export const th = 'whitespace-nowrap border-b border-stone-200 bg-stone-50 px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-stone-500'
export const td = 'whitespace-nowrap border-b border-stone-100 px-3 py-2 text-stone-800'
export const tdNum = `${td} text-right tabular-nums`

export function Loading() {
  return <div className="py-10 text-center text-sm text-stone-400">Загрузка…</div>
}
