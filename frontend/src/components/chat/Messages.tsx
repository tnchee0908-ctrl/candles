import type { ReactNode } from 'react';
import { Check, Loader2, Square, SquareTerminal, X, CircleAlert } from 'lucide-react';
import { cn } from '@/lib/cn';
import { Banner, Tag } from '@/components/ui';
import type { ChatFile, ResponseStatus, ToolCall } from './types';
import { FileChip } from './Files';

/* ---------- Сообщение пользователя: справа, компактный нейтральный блок ---------- */

export function UserMessage({ text, files }: { text: string; files?: ChatFile[] }) {
  return (
    <div className="flex max-w-[72%] flex-col items-end gap-1.5 self-end">
      <div className="whitespace-pre-line rounded-lg bg-hover px-3 py-2 text-fg">{text}</div>
      {files?.map((f) => <FileChip key={f.name} file={f} />)}
    </div>
  );
}

/* ---------- Ответ ассистента: на всю ширину ленты, без рамки ---------- */

interface AssistantMessageProps {
  /** Отрендеренный Markdown (react-markdown или существующий рендерер проекта) */
  children?: ReactNode;
  status?: ResponseStatus;
  /** Блоки под текстом: график, код, файлы, карточка подтверждения */
  attachments?: ReactNode;
  footer?: ReactNode;
}

export function AssistantMessage({ children, status = { kind: 'done' }, attachments, footer }: AssistantMessageProps) {
  return (
    <article className="flex min-w-0 flex-col gap-3" aria-live={status.kind === 'streaming' ? 'polite' : undefined}>
      {status.kind === 'thinking' && <Thinking />}
      {status.kind === 'tool' && <ToolRunning label={status.label} tool={status.tool} />}
      {children && (
        <div className="prose-chat">
          {children}
          {status.kind === 'streaming' && <Caret />}
        </div>
      )}
      {attachments}
      {status.kind === 'interrupted' && (
        <div className="flex items-center gap-2 self-start rounded border border-warning-border bg-warning-bg/60 px-2.5 py-1.5 text-sm text-warning-fg">
          <Square className="size-3.5 text-warning-icon" aria-hidden />
          {status.message ?? 'Ответ прерван пользователем'}
        </div>
      )}
      {status.kind === 'error' && <Banner tone="error">{status.message}</Banner>}
      {footer}
    </article>
  );
}

function Thinking() {
  return (
    <span className="inline-flex items-center gap-2 text-sm text-fg-secondary" role="status">
      <span className="inline-flex gap-[3px]" aria-hidden>
        {[0, 150, 300].map((d) => (
          <i key={d} className="size-[5px] animate-blink rounded-full bg-fg-faint" style={{ animationDelay: `${d}ms` }} />
        ))}
      </span>
      Думает…
    </span>
  );
}

function ToolRunning({ label, tool }: { label: string; tool: string }) {
  return (
    <span className="inline-flex items-center gap-2 text-sm text-fg-secondary" role="status">
      <Loader2 className="size-3.5 animate-spin" aria-hidden />
      {label}
      <span className="font-mono text-xs text-fg-subtle">{tool}</span>
    </span>
  );
}

function Caret() {
  return <span className="ml-0.5 inline-block h-4 w-[7px] animate-blink bg-accent align-[-3px]" aria-hidden />;
}

/* ---------- Подвал ответа: модель, инструменты, Code Interpreter ---------- */

interface MessageFooterProps {
  model: string;
  /** Ответила резервная модель */
  fallback?: boolean;
  tools?: ToolCall[];
  codeRuns?: number;
}

export function MessageFooter({ model, fallback, tools = [], codeRuns = 0 }: MessageFooterProps) {
  return (
    <div className="flex flex-wrap items-center gap-1.5 text-xs text-fg-muted">
      <span className="font-mono text-[11.5px]" title="Модель">
        {model}
      </span>
      {fallback && <Tag className="cursor-help">запасная модель</Tag>}
      {(tools.length > 0 || codeRuns > 0) && <span aria-hidden>·</span>}
      {tools.map((t, i) => (
        <span
          key={`${t.name}-${i}`}
          title={t.detail}
          className={cn(
            'inline-flex h-[22px] items-center gap-[5px] rounded-sm border bg-surface px-[7px]',
            t.ok ? 'border-border text-fg-secondary' : 'border-danger-border text-danger-fg',
          )}
        >
          {t.ok ? <Check className="size-3 text-success-dot" aria-label="успешно" /> : <X className="size-3 text-danger-dot" aria-label="ошибка" />}
          {t.name}
        </span>
      ))}
      {codeRuns > 0 && (
        <span className="inline-flex h-[22px] items-center gap-[5px] rounded-sm border border-border bg-surface px-[7px] text-fg-secondary">
          <SquareTerminal className="size-3" aria-hidden />
          Code Interpreter ×{codeRuns}
        </span>
      )}
    </div>
  );
}

/** Ошибка в ленте с повтором */
export function ChatError({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <Banner tone="error">
      <span className="inline-flex flex-wrap items-center gap-1">
        <CircleAlert className="sr-only" aria-hidden />
        {message}
        {onRetry && (
          <button type="button" onClick={onRetry} className="font-medium text-accent hover:underline">
            Повторить
          </button>
        )}
      </span>
    </Banner>
  );
}
