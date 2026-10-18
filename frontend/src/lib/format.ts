/**
 * Единые правила форматирования данных.
 *  6.0000      → 6
 *  20.3240     → 20,324
 *  24366.75 ₽  → 24 366,75 ₽
 *  2026-10-16  → 16.10.2026
 */

export type Unit = string;
export type Currency = 'RUB' | 'USD' | 'EUR';

const qtyFormatter = new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 4 });
const moneyFormatter = new Intl.NumberFormat('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const priceFormatter = new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 4 });

/** Количество без лишних нулей: "6.0000" → "6", "1000" → "1 000". */
export function formatQty(value: number | string): string {
  return qtyFormatter.format(Number(value));
}

/** Количество с единицей: "6 кг". */
export function formatQtyUnit(value: number | string, unit: Unit): string {
  return `${formatQty(value)} ${unit}`;
}

/** Деньги: в рублях со знаком ₽, в валюте — с кодом. */
export function formatMoney(value: number | string, currency: Currency = 'RUB'): string {
  const n = moneyFormatter.format(Number(value));
  return currency === 'RUB' ? `${n} ₽` : `${n} ${currency}`;
}

/** Цена поставщика: как пришла, без принудительных двух знаков (0,13 / 540). */
export function formatPrice(value: number | string): string {
  return priceFormatter.format(Number(value));
}

/** Процент со знаком: +5,01 %. */
export function formatPercent(value: number, signed = true): string {
  const s = new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 2 }).format(value);
  return `${signed && value > 0 ? '+' : ''}${s} %`;
}

function toDate(value: string | Date): Date {
  if (value instanceof Date) return value;
  // "2026-10-16" трактуем как локальную дату, а не UTC-полночь
  if (/^\d{4}-\d{2}-\d{2}$/.test(value)) {
    const [y, m, d] = value.split('-').map(Number);
    return new Date(y, m - 1, d);
  }
  return new Date(value);
}

const pad = (n: number) => String(n).padStart(2, '0');

/** ДД.ММ.ГГГГ */
export function formatDate(value: string | Date): string {
  const d = toDate(value);
  return `${pad(d.getDate())}.${pad(d.getMonth() + 1)}.${d.getFullYear()}`;
}

/** ДД.ММ.ГГГГ, ЧЧ:ММ */
export function formatDateTime(value: string | Date): string {
  const d = toDate(value);
  return `${formatDate(d)}, ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/** «Смирнова Анна Олеговна» → «Смирнова А. О.» */
export function shortName(fullName: string): string {
  const [last, first, middle] = fullName.split(' ');
  return [last, first && `${first[0]}.`, middle && `${middle[0]}.`].filter(Boolean).join(' ');
}

/** «Смирнова Анна Олеговна» → «СА» */
export function initials(fullName: string): string {
  const [last, first] = fullName.split(' ');
  return `${last?.[0] ?? ''}${first?.[0] ?? ''}`.toUpperCase();
}

/**
 * Дата «сегодня + offset дней» в формате YYYY-MM-DD по времени мастерской (Москва), как на бэкенде.
 * toISOString() дал бы дату по UTC: с 00:00 до 03:00 МСК — вчерашнюю.
 */
export function businessDate(offset = 0): string {
  const today = new Intl.DateTimeFormat('sv-SE', { timeZone: 'Europe/Moscow' }).format(new Date());
  const d = new Date(`${today}T12:00:00Z`);
  d.setUTCDate(d.getUTCDate() + offset);
  return d.toISOString().slice(0, 10);
}
