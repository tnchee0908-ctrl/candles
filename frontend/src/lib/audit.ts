import type { AuditEntry } from '@/types';
import { formatDate, formatDateTime, formatMoney, formatQty, type Currency, type Unit } from './format';

/**
 * Перевод сырых изменений из аудита (status: draft → planned, qty: 6.0000)
 * в человеческий вид для таймлайна и журнала.
 */

export const FIELD_LABELS: Record<string, string> = {
  qty: 'Количество',
  price: 'Цена',
  status: 'Статус',
  comment: 'Комментарий',
  currency: 'Валюта',
  material: 'Материал',
  reserved_qty: 'В резерве',
  remaining_qty: 'Остаток',
  workshop: 'Цех',
  planned_date: 'Плановая дата',
  recipe: 'Продукт',
  items: 'Компоненты',
  code: 'Код',
  name: 'Название',
  unit: 'Единица',
  text: 'Текст',
};

export const STATUS_LABELS: Record<string, string> = {
  // партии
  on_check: 'На проверке',
  accepted: 'Принята',
  rejected: 'Брак',
  // задания
  draft: 'Черновик',
  planned: 'Запланировано',
  in_progress: 'В работе',
  completed: 'Завершено',
  cancelled: 'Отменено',
};

/** Порядок полей в описании: сначала «что», потом «сколько», потом статус. */
const FIELD_ORDER = ['material', 'recipe', 'code', 'name', 'unit', 'qty', 'price', 'workshop', 'planned_date', 'status', 'comment', 'items'];
const fieldRank = (f: string) => (FIELD_ORDER.includes(f) ? FIELD_ORDER.indexOf(f) : FIELD_ORDER.length);

/** Поля, которые не показываем при создании объекта — они выводятся из других. */
const HIDDEN_ON_CREATE = new Set(['reserved_qty', 'remaining_qty', 'currency']);

export interface RawChange {
  field: string;
  from?: unknown;
  to?: unknown;
}

export interface Change {
  field: string;
  label: string;
  from?: string;
  to: string;
}

export interface HumanizeContext {
  unit?: Unit;
  currency?: Currency;
}

export function humanizeValue(field: string, value: unknown, ctx: HumanizeContext = {}): string {
  if (value === null || value === undefined || value === '') return '—';
  switch (field) {
    case 'status':
      return STATUS_LABELS[String(value)] ?? String(value);
    case 'qty':
    case 'reserved_qty':
    case 'remaining_qty':
      return ctx.unit ? `${formatQty(value as number)} ${ctx.unit}` : formatQty(value as number);
    case 'price':
      return ctx.currency ? formatMoney(value as number, ctx.currency) : formatQty(value as number);
    case 'planned_date':
      return formatDate(String(value));
    case 'items':
      return typeof value === 'object' ? `${Object.keys(value as object).length} компонентов` : String(value);
    default:
      return String(value);
  }
}

/** Сырые изменения → строки для <Timeline/>. `isCreate` скрывает производные поля. */
export function humanizeChanges(raw: RawChange[], ctx: HumanizeContext = {}, isCreate = false): Change[] {
  return [...raw]
    .sort((a, b) => fieldRank(a.field) - fieldRank(b.field))
    .filter((c) => !(isCreate && HIDDEN_ON_CREATE.has(c.field)))
    .map((c) => ({
      field: c.field,
      label: FIELD_LABELS[c.field] ?? c.field,
      from: c.from === undefined ? undefined : humanizeValue(c.field, c.from, ctx),
      to: humanizeValue(c.field, c.to, ctx),
    }));
}

/* ---------- записи журнала с сервера ---------- */

interface ComponentSnapshot {
  required?: string;
  reserved?: string;
  actual?: string | null;
}

function componentsChange(
  before: Record<string, ComponentSnapshot> | undefined,
  after: Record<string, ComponentSnapshot>,
): Change | null {
  const all = Object.values(after);
  const hadFact = before && Object.values(before).some((c) => c.actual != null);
  if (!hadFact && all.some((c) => c.actual != null)) {
    return { field: 'components', label: 'Факт', to: `внесён по ${all.length} материалам` };
  }
  const full = (xs: ComponentSnapshot[]) => xs.filter((c) => Number(c.reserved) >= Number(c.required)).length;
  const from = before ? full(Object.values(before)) : 0;
  const to = full(all);
  if (from !== to)
    return { field: 'components', label: 'Полный резерв', from: `${from} из ${all.length}`, to: `${to} из ${all.length}` };
  // Число полностью зарезервированных не изменилось, но резерв вырос (дорезерв части дефицита) —
  // показываем это, а не прочерк в «Было».
  const grown = before
    ? Object.entries(after).filter(([id, c]) => Number(c.reserved) > Number(before[id]?.reserved ?? 0)).length
    : 0;
  if (!grown) return null;
  return {
    field: 'components',
    label: 'Резерв',
    from: `полный по ${from} из ${all.length}`,
    to: `дозарезервировано по ${grown} из ${all.length}`,
  };
}

/**
 * Снимки «было/стало» из журнала → изменения для <Timeline/> и журнала.
 * При создании (before = null) показываем значимые поля, при изменении — только то, что поменялось.
 */
export function auditChanges(entry: AuditEntry, ctx: HumanizeContext = {}): Change[] {
  const after = (entry.after ?? {}) as Record<string, unknown>;
  const before = entry.before as Record<string, unknown> | null;
  const context = { ...ctx, currency: (after.currency as Currency | undefined) ?? ctx.currency };
  if (!before) {
    const raw = Object.entries(after)
      .filter(([k, v]) => k !== 'components' && v !== null && v !== undefined && v !== '')
      .map(([field, to]) => ({ field, to }));
    return humanizeChanges(raw, context, true);
  }
  const raw: RawChange[] = Object.entries(after)
    .filter(([k, v]) => k !== 'components' && JSON.stringify(before[k]) !== JSON.stringify(v))
    .map(([field, to]) => ({ field, from: before[field], to }));
  const changes = humanizeChanges(raw, context);
  if (after.components && JSON.stringify(before.components) !== JSON.stringify(after.components)) {
    const c = componentsChange(
      before.components as Record<string, ComponentSnapshot> | undefined,
      after.components as Record<string, ComponentSnapshot>,
    );
    if (c) changes.push(c);
  }
  return changes;
}

export function auditToEvent(entry: AuditEntry, ctx: HumanizeContext = {}) {
  return {
    id: String(entry.id),
    title: entry.action,
    at: formatDateTime(entry.at),
    actor: entry.user_full_name,
    viaAssistant: entry.via_assistant,
    changes: auditChanges(entry, ctx),
  };
}

/** Строки «Было» и «Стало» для таблицы журнала. */
export function auditSummary(changes: Change[]): { before?: string; after: string } {
  const before = changes.filter((c) => c.from !== undefined).map((c) => `${c.label}: ${c.from}`);
  return {
    before: before.length ? before.join(' · ') : undefined,
    after: changes.map((c) => `${c.label}: ${c.to}`).join(' · ') || '—',
  };
}
