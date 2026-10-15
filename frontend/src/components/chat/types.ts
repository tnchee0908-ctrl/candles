import type { ReserveLevel } from '@/components/ui/ReserveDot';
import type { Unit } from '@/lib/format';

export interface ToolCall {
  name: string; // get_shortages
  ok: boolean;
  /** Подсказка в тултипе: «выполнен за 0,3 с» / текст ошибки */
  detail?: string;
}

export interface CodeRun {
  code: string;
  output?: string;
}

export interface ChatFile {
  kind: 'image' | 'csv' | 'xlsx' | 'file';
  name: string;
  size?: string; // «48 КБ»
  /** Адрес превью картинки (object URL, файлы отдаются только с токеном) */
  url?: string;
  onDownload?: () => void;
}

export function fileKind(name: string, mime = ''): ChatFile['kind'] {
  const n = name.toLowerCase();
  if (mime.startsWith('image/')) return 'image';
  if (n.endsWith('.csv')) return 'csv';
  if (n.endsWith('.xlsx')) return 'xlsx';
  return 'file';
}

export interface ConfirmRow {
  level: ReserveLevel;
  material: string;
  need: number;
  free: number;
  deficit?: number;
  unit: Unit;
}

export type ConfirmState =
  | { kind: 'pending' }
  | { kind: 'submitting' }
  | { kind: 'confirmed'; at: string; orderNo: string; orderUrl: string; deficitNote?: string }
  | { kind: 'rejected' }
  | { kind: 'failed'; error: string };

export interface ConfirmAction {
  id: string;
  title: string; // «Создать и запланировать задание: …»
  rows: ConfirmRow[];
  /** Текст про частичный резерв, если есть дефицит */
  warning?: string;
  state: ConfirmState;
}

export type ResponseStatus =
  | { kind: 'thinking' }
  | { kind: 'tool'; tool: string; label: string } // «Выполняется инструмент: дефицит…»
  | { kind: 'streaming' }
  | { kind: 'done' }
  | { kind: 'interrupted'; message?: string }
  | { kind: 'error'; message: string };

export interface Conversation {
  id: string;
  title: string;
  group: string; // «Сегодня», «Вчера», «Ранее»
}
