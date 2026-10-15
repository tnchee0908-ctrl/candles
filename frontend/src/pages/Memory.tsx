import { Bookmark, Lock, Plus, Trash2 } from 'lucide-react'
import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { api } from '@/api'
import { Page } from '@/components/layout/AppShell'
import {
  Banner,
  Button,
  Card,
  CardBody,
  CardFooter,
  CardHeader,
  EmptyState,
  Input,
  PageHeader,
  Skeleton,
} from '@/components/ui'
import { formatDateTime } from '@/lib/format'
import type { Fact } from '@/types'

/** 17 — Память ассистента: факты о пользователе, добавление вручную, очистка. */
export default function MemoryPage() {
  const [facts, setFacts] = useState<Fact[] | null>(null)
  const [draft, setDraft] = useState('')
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(() => {
    api<Fact[]>('/api/chat/memory')
      .then(setFacts)
      .catch((e) => setError(e.message))
  }, [])
  useEffect(load, [load])

  async function run(fn: () => Promise<unknown>) {
    setError(null)
    try {
      await fn()
      load()
    } catch (e) {
      setError((e as Error).message)
    }
  }

  const add = (e: FormEvent) => {
    e.preventDefault()
    const text = draft.trim()
    if (!text) return
    run(() => api('/api/chat/memory', { method: 'POST', json: { text } }).then(() => setDraft('')))
  }

  return (
    <Page narrow>
      <PageHeader
        title="Память ассистента"
        subtitle="Факты о вас, которые ассистент учитывает во всех ваших диалогах."
      />
      {error && <Banner tone="error" className="mb-4">{error}</Banner>}
      <Card>
        <CardHeader
          title={
            <>
              Факты <span className="ml-1 text-xs font-normal text-fg-muted">{facts?.length ?? ''}</span>
            </>
          }
          actions={
            <span className="inline-flex items-center gap-1.5 text-xs text-fg-muted">
              <Lock className="size-3.5" aria-hidden />
              Видны только вам
            </span>
          }
        />
        {!facts ? (
          <div className="flex flex-col gap-4 px-5 py-4">
            <Skeleton className="w-2/3" />
            <Skeleton className="w-1/2" />
          </div>
        ) : facts.length === 0 ? (
          <EmptyState
            icon={<Bookmark />}
            title="Пока пусто"
            description="Скажите ассистенту, например: «запомни, мой цех — второй» — или добавьте факт вручную."
          />
        ) : (
          <ul>
            {facts.map((f) => (
              <li key={f.id} className="flex items-center gap-3 border-b border-border-soft py-3 pl-5 pr-3 hover:bg-subtle">
                <div className="min-w-0 flex-1">
                  <div>{f.text}</div>
                  <div className="mt-0.5 text-xs text-fg-muted">{formatDateTime(f.created_at)}</div>
                </div>
                <Button
                  variant="ghost"
                  size="sm"
                  icon={<Trash2 />}
                  aria-label={`Удалить факт «${f.text}»`}
                  onClick={() => run(() => api(`/api/chat/memory/${f.id}`, { method: 'DELETE' }))}
                >
                  Удалить
                </Button>
              </li>
            ))}
          </ul>
        )}
        <CardBody>
          <form onSubmit={add} className="flex gap-2">
            <Input
              aria-label="Новый факт"
              maxLength={300}
              placeholder="Добавить факт вручную, например: «Планирую задания по пятницам»"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
            />
            <Button type="submit" icon={<Plus />} disabled={!draft.trim()}>
              Добавить
            </Button>
          </form>
        </CardBody>
        <CardFooter>
          <span className="text-xs text-fg-muted">
            Ассистент сам запоминает факты из диалогов — вы видите и удаляете любой из них.
          </span>
          <Button
            variant="danger"
            size="sm"
            disabled={!facts?.length}
            onClick={() => run(() => api('/api/chat/memory', { method: 'DELETE' }))}
          >
            Очистить всё
          </Button>
        </CardFooter>
      </Card>
    </Page>
  )
}
