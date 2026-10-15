import { dateTime } from '../format'
import type { AuditEntry } from '../types'

function diff(before: Record<string, unknown> | null, after: Record<string, unknown> | null): string[] {
  if (!after) return []
  const lines: string[] = []
  for (const [k, v] of Object.entries(after)) {
    const prev = before?.[k]
    if (k === 'components') continue
    if (JSON.stringify(prev) !== JSON.stringify(v)) {
      lines.push(before ? `${k}: ${fmt(prev)} → ${fmt(v)}` : `${k}: ${fmt(v)}`)
    }
  }
  return lines
}

function fmt(v: unknown): string {
  if (v === null || v === undefined) return '—'
  return typeof v === 'object' ? JSON.stringify(v) : String(v)
}

/** Журнал изменений сущности: кто (ФИО), когда, что было и что стало. */
export default function History({ entries }: { entries: AuditEntry[] }) {
  if (!entries.length) return <div className="text-sm text-stone-400">Изменений нет</div>
  return (
    <ol className="space-y-3">
      {entries.map((e) => (
        <li key={e.id} className="border-l-2 border-wax-200 pl-3 text-sm">
          <div className="flex flex-wrap items-baseline gap-x-2">
            <span className="font-medium">{e.action}</span>
            <span className="text-xs text-stone-500">
              {dateTime(e.at)} · {e.user_full_name}
              {e.via_assistant && <span className="ml-1 rounded bg-violet-100 px-1 text-violet-700">через ассистента</span>}
            </span>
          </div>
          <ul className="mt-0.5 text-xs text-stone-500">
            {diff(e.before, e.after).map((l) => (
              <li key={l} className="font-mono">
                {l}
              </li>
            ))}
          </ul>
        </li>
      ))}
    </ol>
  )
}
