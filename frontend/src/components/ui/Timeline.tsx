import { MessageSquare } from 'lucide-react';
import type { Change } from '@/lib/audit';
import { cn } from '@/lib/cn';
import { Tag } from './Badge';

export interface TimelineEvent {
  id: string;
  title: string; // «Задание запланировано»
  at: string; // уже отформатировано: 15.10.2026, 10:30
  actor: string; // ФИО
  viaAssistant?: boolean;
  changes: Change[]; // из humanizeChanges()
}

/** История изменений: кто, когда, что было → что стало. Последнее событие подсвечено акцентом. */
export function Timeline({ events }: { events: TimelineEvent[] }) {
  return (
    <ol className="ml-1 mt-1 border-l border-border pl-5">
      {events.map((ev, i) => (
        <li key={ev.id} className="relative pb-5 last:pb-0">
          <span
            aria-hidden
            className={cn(
              'absolute -left-[25px] top-[5px] size-[9px] rounded-full border-2 bg-surface',
              i === events.length - 1 ? 'border-accent' : 'border-border-hover',
            )}
          />
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <span className="font-semibold">{ev.title}</span>
            <span className="text-xs text-fg-muted">
              {ev.at} · {ev.actor}
            </span>
            {ev.viaAssistant && (
              <Tag>
                <MessageSquare aria-hidden />
                через ассистента
              </Tag>
            )}
          </div>
          {ev.changes.length > 0 && (
            <dl className="mt-1.5 grid grid-cols-[max-content_minmax(0,1fr)] gap-x-4 gap-y-0.5 text-sm leading-5">
              {ev.changes.map((c) => (
                <div key={c.field} className="contents">
                  <dt className="text-fg-muted">{c.label}</dt>
                  <dd className="tabular-nums">
                    {c.from !== undefined && (
                      <>
                        <span className="text-fg-subtle">{c.from}</span>
                        <span className="mx-1.5 text-fg-faint" aria-label="изменено на">
                          →
                        </span>
                      </>
                    )}
                    {c.to}
                  </dd>
                </div>
              ))}
            </dl>
          )}
        </li>
      ))}
    </ol>
  );
}
