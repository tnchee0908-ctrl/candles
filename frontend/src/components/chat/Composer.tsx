import { useLayoutEffect, useRef, useState, type KeyboardEvent } from 'react';
import { ArrowUp, Paperclip, Square } from 'lucide-react';
import { cn } from '@/lib/cn';
import { Button, IconButton } from '@/components/ui';
import { FileChip } from './Files';
import { fileKind, type ChatFile } from './types';

interface ComposerProps {
  onSend: (text: string, files: File[]) => void;
  onStop: () => void;
  /** Ассистент отвечает: вместо «Отправить» — «Остановить» */
  responding?: boolean;
  placeholder?: string;
}

const MAX_HEIGHT = 200;

/**
 * Поле ввода: многострочное, растёт по высоте, прижато к низу ленты.
 * Подсказка про клавиши — под полем, а не в placeholder.
 */
export function Composer({ onSend, onStop, responding, placeholder = 'Спросите про остатки, дефицит, себестоимость…' }: ComposerProps) {
  const [text, setText] = useState('');
  const [files, setFiles] = useState<File[]>([]);
  const [focused, setFocused] = useState(false);
  const ta = useRef<HTMLTextAreaElement>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  useLayoutEffect(() => {
    const el = ta.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, MAX_HEIGHT)}px`;
  }, [text]);

  const canSend = !responding && (text.trim().length > 0 || files.length > 0);

  const send = () => {
    if (!canSend) return;
    onSend(text.trim(), files);
    setText('');
    setFiles([]);
  };

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      send();
    }
  };

  const asChip = (f: File): ChatFile => ({
    kind: fileKind(f.name),
    name: f.name,
    size: `${Math.max(1, Math.round(f.size / 1024))} КБ`,
  });

  return (
    <div className="border-t border-border bg-canvas px-8 pb-3.5 pt-3">
      <div
        className={cn(
          'mx-auto max-w-chat rounded-lg border bg-surface pb-2 pl-3 pr-2 pt-2.5 transition-[border-color,box-shadow]',
          focused ? 'border-accent ring-[3px] ring-accent/15' : 'border-border-strong',
        )}
      >
        {files.length > 0 && (
          <div className="mb-2 flex flex-wrap gap-1.5">
            {files.map((f, i) => (
              <FileChip key={f.name + i} file={asChip(f)} onRemove={() => setFiles((xs) => xs.filter((_, j) => j !== i))} />
            ))}
          </div>
        )}
        <textarea
          ref={ta}
          rows={1}
          value={text}
          disabled={responding}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={onKeyDown}
          onFocus={() => setFocused(true)}
          onBlur={() => setFocused(false)}
          placeholder={responding ? 'Ассистент отвечает…' : placeholder}
          aria-label="Сообщение ассистенту"
          className="block min-h-10 w-full resize-none bg-transparent py-0.5 text-base text-fg outline-none placeholder:text-fg-faint disabled:text-fg-faint"
        />
        <div className="mt-1 flex items-center justify-between gap-2">
          <IconButton label="Прикрепить CSV или XLSX" size="sm" disabled={responding} onClick={() => fileInput.current?.click()}>
            <Paperclip />
          </IconButton>
          <input
            ref={fileInput}
            type="file"
            accept=".csv,.xlsx,.txt,.tsv,.json"
            multiple
            hidden
            onChange={(e) => {
              setFiles((xs) => [...xs, ...Array.from(e.target.files ?? [])]);
              e.target.value = '';
            }}
          />
          {responding ? (
            <Button variant="secondary" size="sm" icon={<Square />} onClick={onStop}>
              Остановить
            </Button>
          ) : (
            <Button variant="primary" size="sm" icon={<ArrowUp />} disabled={!canSend} onClick={send}>
              Отправить
            </Button>
          )}
        </div>
      </div>
      <div className="mx-auto mt-1.5 flex max-w-chat justify-between gap-3 text-xs text-fg-subtle">
        <span>
          <Kbd>Enter</Kbd> — отправить, <Kbd>Shift</Kbd>+<Kbd>Enter</Kbd> — новая строка
        </span>
        <span>CSV, XLSX · до 5 МБ</span>
      </div>
    </div>
  );
}

function Kbd({ children }: { children: string }) {
  return (
    <kbd className="rounded-sm border border-b-2 border-border bg-surface px-1 font-mono text-[11px] text-fg-secondary">{children}</kbd>
  );
}
