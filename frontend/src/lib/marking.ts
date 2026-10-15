import type { MarkingAttempt } from '@/types'

/** Пояснение к попытке: «OK», «Таймаут 5 с»… Текст «HTTP 500» не повторяем — код и так виден. */
export function attemptNote(a: MarkingAttempt, ok = 'OK'): string {
  if (!a.error) return ok
  return a.status_code && a.error === `HTTP ${a.status_code}` ? 'ошибка сервера' : a.error
}
