import { Plus, Trash2 } from 'lucide-react';
import { cn } from '@/lib/cn';
import { Button, IconButton } from '@/components/ui';
import type { Conversation } from './types';

interface ConversationListProps {
  items: Conversation[];
  activeId?: string;
  onSelect: (id: string) => void;
  onNew: () => void;
  onDelete: (id: string) => void;
}

/** Колонка диалогов 260 px: «Новый диалог», группы по дате, удаление по наведению. */
export function ConversationList({ items, activeId, onSelect, onNew, onDelete }: ConversationListProps) {
  const groups = Array.from(new Set(items.map((i) => i.group)));
  return (
    <nav aria-label="Диалоги" className="flex w-chatlist shrink-0 flex-col gap-0.5 overflow-y-auto border-r border-border bg-[#FBFAF8] px-2.5 py-3">
      <Button variant="secondary" icon={<Plus />} fullWidth onClick={onNew}>
        Новый диалог
      </Button>
      {groups.map((g) => (
        <div key={g} className="flex flex-col gap-0.5">
          <div className="px-2 pb-1.5 pt-3.5 text-2xs font-medium uppercase tracking-[0.06em] text-fg-subtle">{g}</div>
          {items
            .filter((i) => i.group === g)
            .map((c) => {
              const active = c.id === activeId;
              return (
                <div
                  key={c.id}
                  className={cn(
                    'group flex h-[34px] items-center gap-1.5 rounded pl-2.5 pr-1 text-sm transition-colors',
                    active ? 'bg-surface font-medium text-fg shadow-[inset_0_0_0_1px_rgb(var(--c-border))]' : 'text-fg-label hover:bg-muted hover:text-fg',
                  )}
                >
                  <button
                    type="button"
                    onClick={() => onSelect(c.id)}
                    aria-current={active ? 'page' : undefined}
                    className="min-w-0 flex-1 truncate text-left focus-visible:outline-none"
                    title={c.title}
                  >
                    {c.title}
                  </button>
                  <IconButton
                    label="Удалить диалог"
                    size="sm"
                    tone="danger"
                    onClick={() => onDelete(c.id)}
                    className="invisible group-focus-within:visible group-hover:visible [&_svg]:size-3.5"
                  >
                    <Trash2 />
                  </IconButton>
                </div>
              );
            })}
        </div>
      ))}
    </nav>
  );
}
