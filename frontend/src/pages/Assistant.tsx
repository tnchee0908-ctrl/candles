import { useCallback, useEffect, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import { Link, useNavigate, useParams } from 'react-router-dom'
import remarkGfm from 'remark-gfm'
import { api, authHeaders, downloadFile, fetchBlobUrl, postStream, type SseEvent } from '../api'
import PreviewTable from '../components/PreviewTable'
import { Button, ErrorBox } from '../components/ui'
import { day } from '../format'
import type { ChatAction, ChatFile, ChatMessage, CodeRun, Conversation } from '../types'

const TOOL_TITLES: Record<string, string> = {
  get_material_stock: 'остатки',
  get_shortages: 'дефицит',
  get_batch_history: 'история партии',
  get_order_cost: 'себестоимость',
  list_orders: 'задания',
  list_recipes: 'рецепты',
  find_batches: 'поиск партий',
  get_currency_rate: 'курс валют',
  propose_production_order: 'подготовка задания',
  remember_fact: 'память',
  export_dataset: 'выгрузка в песочницу',
}

const EXAMPLES = [
  'Чего не хватит на задания этой недели?',
  'Запланируй 200 свечей «Лаванда» на пятницу',
  'Построй график расхода воска по неделям за квартал',
  'Как изменится себестоимость свечи «Лаванда», если соевый воск подорожает на 15%?',
]

export default function AssistantPage() {
  const { conversationId } = useParams()
  const navigate = useNavigate()
  const convId = conversationId ? Number(conversationId) : null
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [text, setText] = useState('')
  const [attachments, setAttachments] = useState<ChatFile[]>([])
  const [streaming, setStreaming] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const abortRef = useRef<AbortController | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)
  const fileInput = useRef<HTMLInputElement>(null)
  // Диалог, который мы только что создали сами при отправке: его сообщения уже на экране, перечитывать не надо.
  const justCreated = useRef<number | null>(null)

  const loadConversations = useCallback(() => {
    api<Conversation[]>('/api/chat/conversations').then(setConversations).catch((e) => setError(e.message))
  }, [])

  const loadMessages = useCallback(async (id: number) => {
    try {
      setMessages(await api<ChatMessage[]>(`/api/chat/conversations/${id}/messages`))
    } catch (e) {
      setError((e as Error).message)
    }
  }, [])

  useEffect(loadConversations, [loadConversations])
  useEffect(() => {
    if (convId !== null && justCreated.current === convId) {
      justCreated.current = null
      return
    }
    setMessages([])
    setError(null)
    if (convId) loadMessages(convId)
  }, [convId, loadMessages])
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const patchLast = (fn: (m: ChatMessage) => ChatMessage) =>
    setMessages((ms) => (ms.length ? [...ms.slice(0, -1), fn(ms[ms.length - 1])] : ms))

  function onEvent(e: SseEvent) {
    switch (e.type) {
      case 'start':
        setMessages((ms) => {
          const copy = [...ms]
          copy[copy.length - 2] = { ...copy[copy.length - 2], id: e.user_message_id as number }
          copy[copy.length - 1] = { ...copy[copy.length - 1], id: e.assistant_message_id as number }
          return copy
        })
        break
      case 'delta':
        patchLast((m) => ({ ...m, content: m.content + (e.text as string) }))
        break
      case 'model':
        patchLast((m) => ({ ...m, model: e.model as string }))
        break
      case 'tool':
        if (e.status === 'start') patchLast((m) => ({ ...m, running_tools: [...(m.running_tools ?? []), e.name as string] }))
        else
          patchLast((m) => ({
            ...m,
            running_tools: (m.running_tools ?? []).filter((t) => t !== e.name),
            tool_calls: [...m.tool_calls, { name: e.name as string, ok: e.status === 'ok', summary: e.summary as string, arguments: null }],
          }))
        break
      case 'code':
        patchLast((m) => ({ ...m, code: [...m.code, { code: e.code as string, logs: e.logs as string, error: Boolean(e.error) }] }))
        break
      case 'action':
        patchLast((m) => ({ ...m, actions: [...m.actions, e.action as ChatAction] }))
        break
      case 'file':
        patchLast((m) => ({ ...m, files: [...m.files, e.file as ChatFile] }))
        break
      case 'done':
        patchLast(() => e.message as ChatMessage)
        break
      case 'error':
        setError(e.message as string)
        break
    }
  }

  async function ensureConversation(): Promise<number> {
    if (convId) return convId
    const conv = await api<Conversation>('/api/chat/conversations', { method: 'POST' })
    justCreated.current = conv.id
    navigate(`/assistant/${conv.id}`, { replace: true })
    return conv.id
  }

  async function send(question = text) {
    const q = question.trim()
    if (!q || streaming) return
    setError(null)
    const id = await ensureConversation()
    const files = attachments
    setText('')
    setAttachments([])
    const now = new Date().toISOString()
    setMessages((ms) => [
      ...ms,
      { id: -1, role: 'user', content: q, status: 'complete', model: null, tool_calls: [], code: [], files, actions: [], error: null, created_at: now },
      { id: -2, role: 'assistant', content: '', status: 'streaming', model: null, tool_calls: [], code: [], files: [], actions: [], error: null, running_tools: [] },
    ])
    const controller = new AbortController()
    abortRef.current = controller
    setStreaming(true)
    try {
      await postStream(`/api/chat/conversations/${id}/messages`, { text: q, file_ids: files.map((f) => f.id) }, onEvent, controller.signal)
    } catch (e) {
      if ((e as Error).name !== 'AbortError') {
        setError((e as Error).message)
        // Сервер отказал до начала ответа — убираем черновые пузыри (у них отрицательные id).
        setMessages((ms) => ms.filter((m) => m.id > 0))
        setText(q)
      }
    } finally {
      setStreaming(false)
      abortRef.current = null
      loadConversations()
      // После «Остановить» сервер сохраняет часть ответа с пометкой — подтягиваем итог.
      if (controller.signal.aborted) setTimeout(() => loadMessages(id), 600)
    }
  }

  async function stop() {
    if (convId) await fetch(`/api/chat/conversations/${convId}/stop`, { method: 'POST', headers: authHeaders() })
    abortRef.current?.abort()
  }

  async function upload(file: File) {
    try {
      const id = await ensureConversation()
      const form = new FormData()
      form.append('file', file)
      const resp = await fetch(`/api/chat/conversations/${id}/files`, { method: 'POST', headers: authHeaders(), body: form })
      const body = await resp.json()
      if (!resp.ok) throw new Error(body.detail ?? 'Не удалось загрузить файл')
      setAttachments((a) => [...a, body as ChatFile])
    } catch (e) {
      setError((e as Error).message)
    }
  }

  async function decide(action: ChatAction, decision: 'confirm' | 'reject') {
    try {
      await api(`/api/chat/actions/${action.id}/${decision}`, { method: 'POST' })
    } catch (e) {
      setError((e as Error).message)
    }
    if (convId) loadMessages(convId)
  }

  async function removeConversation(id: number) {
    await api(`/api/chat/conversations/${id}`, { method: 'DELETE' })
    loadConversations()
    if (id === convId) navigate('/assistant')
  }

  return (
    <div className="-m-6 flex h-screen">
      <div className="flex w-60 shrink-0 flex-col border-r border-stone-200 bg-white/60">
        <div className="p-3">
          <Button className="w-full" onClick={() => navigate('/assistant')}>
            + Новый диалог
          </Button>
        </div>
        <div className="flex-1 overflow-y-auto px-2 pb-3">
          {conversations.map((c) => (
            <div
              key={c.id}
              className={`group flex items-center justify-between rounded-md px-2 py-1.5 text-sm ${c.id === convId ? 'bg-wax-100' : 'hover:bg-stone-100'}`}
            >
              <Link to={`/assistant/${c.id}`} className="min-w-0 flex-1 truncate">
                {c.title}
              </Link>
              <button className="ml-1 hidden text-stone-400 hover:text-red-600 group-hover:block" onClick={() => removeConversation(c.id)} title="Удалить">
                ✕
              </button>
            </div>
          ))}
        </div>
      </div>

      <div className="flex min-w-0 flex-1 flex-col">
        <div className="flex-1 overflow-y-auto px-6 py-6">
          <div className="mx-auto max-w-3xl space-y-5">
            {!messages.length && (
              <div className="pt-10 text-center">
                <h1 className="text-xl font-semibold">Ассистент мастерской</h1>
                <p className="mt-1 text-sm text-stone-500">
                  Отвечает по данным учёта, считает в Code Interpreter и готовит задания — изменения только после вашего «Подтвердить».
                </p>
                <div className="mx-auto mt-6 grid max-w-xl gap-2 sm:grid-cols-2">
                  {EXAMPLES.map((ex) => (
                    <button key={ex} onClick={() => send(ex)} className="rounded-lg border border-stone-200 bg-white p-3 text-left text-sm hover:border-wax-500">
                      {ex}
                    </button>
                  ))}
                </div>
              </div>
            )}
            {messages.map((m, i) =>
              m.role === 'user' ? (
                <UserBubble key={`${m.id}-${i}`} message={m} />
              ) : (
                <AssistantBlock key={`${m.id}-${i}`} message={m} onDecide={decide} />
              ),
            )}
            <div ref={bottomRef} />
          </div>
        </div>

        <div className="border-t border-stone-200 bg-white px-6 py-3">
          <div className="mx-auto max-w-3xl">
            <ErrorBox error={error} />
            {attachments.length > 0 && (
              <div className="mb-2 flex flex-wrap gap-2">
                {attachments.map((f) => (
                  <span key={f.id} className="rounded-full bg-stone-100 px-2 py-0.5 text-xs">
                    📎 {f.filename}
                    <button className="ml-1 text-stone-400" onClick={() => setAttachments((a) => a.filter((x) => x.id !== f.id))}>
                      ✕
                    </button>
                  </span>
                ))}
              </div>
            )}
            <div className="flex items-end gap-2">
              <input
                ref={fileInput}
                type="file"
                accept=".csv,.xlsx,.txt,.tsv,.json"
                className="hidden"
                onChange={(e) => {
                  const f = e.target.files?.[0]
                  if (f) upload(f)
                  e.target.value = ''
                }}
              />
              <Button variant="ghost" title="Прикрепить CSV/XLSX" onClick={() => fileInput.current?.click()} disabled={streaming}>
                📎
              </Button>
              <textarea
                className="max-h-40 min-h-[42px] flex-1 resize-y rounded-md border border-stone-300 px-3 py-2 text-sm focus:border-wax-500 focus:outline-none"
                rows={1}
                placeholder="Спросите про остатки, дефицит, себестоимость… (Enter — отправить, Shift+Enter — новая строка)"
                value={text}
                onChange={(e) => setText(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault()
                    send()
                  }
                }}
              />
              {streaming ? (
                <Button variant="danger" onClick={stop}>
                  ■ Остановить
                </Button>
              ) : (
                <Button onClick={() => send()} disabled={!text.trim()}>
                  Отправить
                </Button>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

function UserBubble({ message }: { message: ChatMessage }) {
  return (
    <div className="flex justify-end">
      <div className="max-w-[80%] rounded-2xl rounded-br-sm bg-wax-600 px-4 py-2 text-sm text-white">
        <div className="whitespace-pre-wrap">{message.content}</div>
        {message.files.length > 0 && (
          <div className="mt-1 text-xs text-wax-100">{message.files.map((f) => `📎 ${f.filename}`).join(', ')}</div>
        )}
      </div>
    </div>
  )
}

function AssistantBlock({ message, onDecide }: { message: ChatMessage; onDecide: (a: ChatAction, d: 'confirm' | 'reject') => Promise<void> }) {
  if (message.system_note) {
    return <div className="text-center text-xs text-stone-500">— {message.content} —</div>
  }
  const thinking = message.status === 'streaming' && !message.content && !message.running_tools?.length
  return (
    <div className="rounded-xl border border-stone-200 bg-white px-4 py-3 shadow-sm">
      {thinking && <div className="animate-pulse text-sm text-stone-400">Думаю…</div>}
      {message.running_tools?.map((t, i) => (
        <div key={i} className="mb-1 animate-pulse text-xs text-violet-700">
          ⚙ {TOOL_TITLES[t] ?? t}…
        </div>
      ))}
      {message.content && (
        <div className="prose-chat text-sm leading-relaxed">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content}</ReactMarkdown>
        </div>
      )}
      {message.files.length > 0 && (
        <div className="mt-3 space-y-2">
          {message.files.map((f) => (
            <FileView key={f.id} file={f} />
          ))}
        </div>
      )}
      {message.actions.map((a) => (
        <ActionCard key={a.id} action={a} onDecide={onDecide} />
      ))}
      {message.status === 'interrupted' && (
        <div className="mt-2 rounded bg-amber-50 px-2 py-1 text-xs text-amber-800">⏸ {message.error ?? 'Ответ прерван'}</div>
      )}
      {message.status === 'error' && <div className="mt-2 rounded bg-red-50 px-2 py-1 text-xs text-red-800">⚠ {message.error}</div>}
      <Footer message={message} />
    </div>
  )
}

function Footer({ message }: { message: ChatMessage }) {
  if (!message.model && !message.tool_calls.length && !message.code.length) return null
  return (
    <div className="mt-3 space-y-1.5 border-t border-stone-100 pt-2 text-xs text-stone-500">
      <div className="flex flex-wrap items-center gap-1.5">
        {message.model && (
          <span className="rounded bg-stone-100 px-1.5 py-0.5 font-mono">
            {message.model}
            {message.fallback_used && <span className="ml-1 text-amber-700">(запасная)</span>}
          </span>
        )}
        {message.tool_calls.map((t, i) => (
          <span
            key={i}
            title={`${t.summary}${t.arguments ? '\n' + JSON.stringify(t.arguments, null, 1) : ''}`}
            className={`rounded px-1.5 py-0.5 ${t.ok ? 'bg-violet-50 text-violet-700' : 'bg-red-50 text-red-700'}`}
          >
            {t.ok ? '✓' : '✗'} {t.name}
          </span>
        ))}
        {message.code.length > 0 && <span className="rounded bg-sky-50 px-1.5 py-0.5 text-sky-700">✓ code_interpreter ×{message.code.length}</span>}
      </div>
      {message.code.map((c, i) => (
        <CodeView key={i} run={c} index={i} />
      ))}
    </div>
  )
}

function CodeView({ run, index }: { run: CodeRun; index: number }) {
  return (
    <details className="rounded border border-stone-200">
      <summary className="cursor-pointer px-2 py-1 text-stone-600">
        Код, выполненный моделью #{index + 1} {run.error && <span className="text-red-600">(ошибка)</span>}
      </summary>
      <pre className="max-h-80 overflow-auto bg-stone-900 p-3 text-[11px] leading-snug text-stone-100">{run.code}</pre>
      {run.logs && <pre className="max-h-40 overflow-auto bg-stone-50 p-2 text-[11px] text-stone-700">{run.logs}</pre>}
    </details>
  )
}

function FileView({ file }: { file: ChatFile }) {
  const [src, setSrc] = useState<string | null>(null)
  const isImage = file.mime.startsWith('image/')
  useEffect(() => {
    if (!isImage) return
    let url: string | null = null
    fetchBlobUrl(`/api/chat/files/${file.id}`).then((u) => {
      url = u
      setSrc(u)
    })
    return () => {
      if (url) URL.revokeObjectURL(url)
    }
  }, [file.id, isImage])
  return (
    <div>
      {isImage && src && <img src={src} alt={file.filename} className="max-h-96 rounded border border-stone-200" />}
      <button className="mt-1 text-xs text-wax-700 hover:underline" onClick={() => downloadFile(`/api/chat/files/${file.id}`, file.filename)}>
        ⬇ {file.filename}
      </button>
    </div>
  )
}

function ActionCard({ action, onDecide }: { action: ChatAction; onDecide: (a: ChatAction, d: 'confirm' | 'reject') => Promise<void> }) {
  const [busy, setBusy] = useState(false)
  const p = action.preview
  const decide = async (d: 'confirm' | 'reject') => {
    setBusy(true)
    await onDecide(action, d)
    setBusy(false)
  }
  return (
    <div className="mt-3 rounded-lg border-2 border-wax-200 bg-wax-50 p-3">
      <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-wax-700">Требуется подтверждение</div>
      <div className="mb-2 text-sm font-medium">{p.title}</div>
      <div className="rounded border border-stone-200 bg-white">
        <PreviewTable rows={p.components} />
      </div>
      {p.has_shortage && (
        <div className="mt-2 text-xs text-amber-800">Будет частичный резерв: запустить задание можно будет только после дорезервирования.</div>
      )}
      <div className="mt-3 flex items-center gap-2">
        {action.status === 'pending' ? (
          <>
            <Button disabled={busy} onClick={() => decide('confirm')}>
              Подтвердить
            </Button>
            <Button variant="secondary" disabled={busy} onClick={() => decide('reject')}>
              Отклонить
            </Button>
            <span className="text-xs text-stone-500">До нажатия ничего не изменится · дата {day(p.planned_date)}</span>
          </>
        ) : action.status === 'confirmed' ? (
          <span className="text-sm text-emerald-700">
            ✓ Подтверждено:{' '}
            <Link className="underline" to={`/orders/${action.result?.order_id}`}>
              задание {action.result?.order_number}
            </Link>
            {action.result?.shortage && <span className="text-amber-700"> · дефицит: {action.result.shortage}</span>}
          </span>
        ) : action.status === 'rejected' ? (
          <span className="text-sm text-stone-500">Отклонено</span>
        ) : (
          <span className="text-sm text-red-700">Не выполнено: {action.result?.error}</span>
        )}
      </div>
    </div>
  )
}
