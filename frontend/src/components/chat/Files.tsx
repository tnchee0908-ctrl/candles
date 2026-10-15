import { useState } from 'react';
import { ChevronDown, ChevronUp, Code2, Download, Image as ImageIcon, X } from 'lucide-react';
import { cn } from '@/lib/cn';
import { Button, IconButton } from '@/components/ui';
import type { ChatFile, CodeRun } from './types';

const typeClass: Record<ChatFile['kind'], string> = {
  csv: 'bg-success-bg text-success-fg',
  xlsx: 'bg-info-bg text-info-fg',
  image: 'bg-neutral-bg text-neutral-fg',
  file: 'bg-neutral-bg text-neutral-fg',
};

function TypeBadge({ file }: { file: ChatFile }) {
  const ext = file.name.includes('.') ? file.name.split('.').pop()!.toUpperCase() : 'FILE';
  return <span className={cn('rounded-[3px] px-1 font-mono text-[10px] font-medium leading-4', typeClass[file.kind])}>{ext}</span>;
}

/** Чип прикреплённого файла (в сообщении пользователя и в поле ввода). */
export function FileChip({ file, onRemove }: { file: ChatFile; onRemove?: () => void }) {
  return (
    <span className="inline-flex h-8 items-center gap-2 rounded border border-border bg-surface pl-2 pr-2.5 text-sm">
      <TypeBadge file={file} />
      {file.name}
      <span className="text-xs text-fg-subtle">{file.size}</span>
      {onRemove && (
        <IconButton label="Убрать файл" size="sm" onClick={onRemove} className="-mr-1.5 size-5 [&_svg]:size-3">
          <X />
        </IconButton>
      )}
    </span>
  );
}

/** Файл от ассистента: картинка — превью в рамке; таблица — строка с типом и размером. */
export function AssistantFile({ file, alt }: { file: ChatFile; alt?: string }) {
  if (file.kind === 'image') {
    return (
      <figure className="m-0 overflow-hidden rounded-lg border border-border bg-surface">
        {file.url ? (
          <img src={file.url} alt={alt ?? file.name} className="block h-auto w-full" />
        ) : (
          <div className="h-48 animate-pulse bg-subtle" aria-label="Загрузка изображения" />
        )}
        <figcaption className="flex items-center justify-between gap-2 border-t border-border-soft py-1.5 pl-3 pr-1.5 text-sm text-fg-secondary">
          <span className="flex min-w-0 items-center gap-1.5">
            <ImageIcon className="size-3.5 shrink-0" aria-hidden />
            <span className="truncate">{file.name}</span>
            <span className="text-fg-subtle">{file.size}</span>
          </span>
          <Button variant="ghost" size="sm" icon={<Download />} onClick={file.onDownload}>
            Скачать
          </Button>
        </figcaption>
      </figure>
    );
  }
  return (
    <div className="flex max-w-[520px] items-center justify-between gap-2 rounded-lg border border-border bg-surface py-1.5 pl-3 pr-1.5">
      <span className="flex min-w-0 items-center gap-2.5">
        <TypeBadge file={file} />
        <span className="truncate">{file.name}</span>
        <span className="text-xs text-fg-subtle">{file.size}</span>
      </span>
      <Button variant="ghost" size="sm" icon={<Download />} onClick={file.onDownload}>
        Скачать
      </Button>
    </div>
  );
}

/** Код, выполненный моделью. Свёрнут по умолчанию; внутри — тёмный блок и вывод. */
export function CodeRunBlock({ run, index = 1, defaultOpen = false }: { run: CodeRun; index?: number; defaultOpen?: boolean }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="overflow-hidden rounded-lg border border-border bg-surface">
      <div className="flex h-9 items-center justify-between gap-2 bg-subtle pl-3 pr-1.5 text-sm text-fg-secondary">
        <span className="flex items-center gap-1.5">
          <Code2 className="size-3.5" aria-hidden />
          Код · запуск #{index}
        </span>
        <Button
          variant="ghost"
          size="sm"
          aria-expanded={open}
          iconRight={open ? <ChevronUp /> : <ChevronDown />}
          onClick={() => setOpen((v) => !v)}
        >
          {open ? 'Скрыть код' : 'Показать код'}
        </Button>
      </div>
      {open && (
        <>
          <pre className="m-0 overflow-x-auto whitespace-pre bg-code-bg px-4 py-3.5 font-mono text-[12.5px] leading-5 text-code-fg">
            <code>{run.code}</code>
          </pre>
          {run.output && (
            <pre className="m-0 overflow-x-auto whitespace-pre border-t border-border bg-subtle px-4 py-2.5 font-mono text-xs leading-[18px] text-fg-label">
              {run.output}
            </pre>
          )}
        </>
      )}
    </div>
  );
}
