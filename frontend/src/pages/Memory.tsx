import { useCallback, useEffect, useState } from 'react'
import { api } from '../api'
import { Button, Card, ErrorBox, PageHeader, inputCls } from '../components/ui'
import { dateTime } from '../format'
import type { Fact } from '../types'

export default function MemoryPage() {
  const [facts, setFacts] = useState<Fact[]>([])
  const [text, setText] = useState('')
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(() => {
    api<Fact[]>('/api/chat/memory').then(setFacts).catch((e) => setError(e.message))
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

  return (
    <div className="max-w-3xl">
      <PageHeader
        title="Память ассистента"
        subtitle="Факты о вас, которые ассистент учитывает во всех ваших диалогах. Другим пользователям они не видны."
      />
      <ErrorBox error={error} />
      <Card>
        {facts.length ? (
          <ul className="divide-y divide-stone-100">
            {facts.map((f) => (
              <li key={f.id} className="flex items-center justify-between gap-3 py-2">
                <div>
                  <div className="text-sm">{f.text}</div>
                  <div className="text-xs text-stone-400">{dateTime(f.created_at)}</div>
                </div>
                <Button variant="ghost" onClick={() => run(() => api(`/api/chat/memory/${f.id}`, { method: 'DELETE' }))}>
                  Удалить
                </Button>
              </li>
            ))}
          </ul>
        ) : (
          <div className="text-sm text-stone-400">
            Пока пусто. Скажите ассистенту, например: «запомни, мой цех — второй» или «считай мне в евро».
          </div>
        )}
        <form
          className="mt-4 flex gap-2"
          onSubmit={(e) => {
            e.preventDefault()
            if (text.trim()) run(() => api('/api/chat/memory', { method: 'POST', json: { text } }).then(() => setText('')))
          }}
        >
          <input className={inputCls} placeholder="Добавить факт вручную" value={text} onChange={(e) => setText(e.target.value)} />
          <Button type="submit">Добавить</Button>
        </form>
        {facts.length > 0 && (
          <div className="mt-3 text-right">
            <Button variant="danger" onClick={() => run(() => api('/api/chat/memory', { method: 'DELETE' }))}>
              Очистить всё
            </Button>
          </div>
        )}
      </Card>
    </div>
  )
}
