const numberFmt = new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 4 })
const moneyFmt = new Intl.NumberFormat('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 })

/** Числа приходят с бэкенда строками (Decimal) — форматируем только для показа. */
export function num(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === '') return '—'
  return numberFmt.format(Number(value))
}

export function money(value: string | number | null | undefined, currency = '₽'): string {
  if (value === null || value === undefined || value === '') return '—'
  return `${moneyFmt.format(Number(value))} ${currency}`
}

export function day(iso: string | null | undefined): string {
  if (!iso) return '—'
  const [y, m, d] = iso.slice(0, 10).split('-')
  return `${d}.${m}.${y}`
}

export function dateTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleString('ru-RU', { dateStyle: 'short', timeStyle: 'short' })
}

export function todayIso(offsetDays = 0): string {
  const d = new Date()
  d.setDate(d.getDate() + offsetDays)
  return d.toISOString().slice(0, 10)
}
