import { CircleCheck } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import ReactMarkdown, { defaultUrlTransform, type Components } from 'react-markdown'
import { useNavigate, useParams } from 'react-router-dom'
import remarkGfm from 'remark-gfm'
import { api, authHeaders, downloadFile, fetchBlobUrl, postStream, type SseEvent } from '@/api'
import {
  AssistantFile,
  AssistantMessage,
  ChatEmpty,
  CodeRunBlock,
  Composer,
  ConfirmActionCard,
  ConversationList,
  MessageFooter,
  UserMessage,
  fileKind,
  type ChatFile as UiFile,
  type ConfirmAction,
  type ResponseStatus,
} from '@/components/chat'
import { Banner } from '@/components/ui'
import { formatDateTime } from '@/lib/format'
import { levelByQty } from '@/lib/reserve'
import type { ChatAction, ChatFile, ChatMessage, Conversation } from '@/types'

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

function dayGroup(iso: string): string {
  const d = new Date(iso)
  const today = new Date()
  const start = new Date(today.getFullYear(), today.getMonth(), today.getDate()).getTime()
  if (d.getTime() >= start) return 'Сегодня'
  if (d.getTime() >= start - 86_400_000) return 'Вчера'
  return 'Ранее'
}

function responseStatus(m: ChatMessage): ResponseStatus {
  if (m.status === 'streaming') {
    const running = m.running_tools?.[m.running_tools.length - 1]
    if (running) return { kind: 'tool', tool: running, label: `Выполняется инструмент: ${TOOL_TITLES[running] ?? running}…` }
    return m.content ? { kind: 'streaming' } : { kind: 'thinking' }
  }
  if (m.status === 'interrupted') return { kind: 'interrupted', message: m.error ?? undefined }
  if (m.status === 'error') return { kind: 'error', message: m.error ?? 'Не удалось получить ответ.' }
  return { kind: 'done' }
}

function toConfirmAction(a: ChatAction, submitting: boolean): ConfirmAction {
  const p = a.preview
  const state: ConfirmAction['state'] = submitting
    ? { kind: 'submitting' }
    : a.status === 'confirmed'
      ? {
          kind: 'confirmed',
          at: a.decided_at ? formatDateTime(a.decided_at) : '',
          orderNo: a.result?.order_number ?? '',
          orderUrl: `/orders/${a.result?.order_id}`,
          deficitNote: a.result?.shortage ? `Дефицит: ${a.result.shortage}.` : undefined,
        }
      : a.status === 'rejected'
        ? { kind: 'rejected' }
        : a.status === 'failed'
          ? { kind: 'failed', error: a.result?.error ?? 'Действие не выполнено.' }
          : { kind: 'pending' }
  return {
    id: `action-${a.id}`,
    title: p.title,
    warning: p.has_shortage ? 'Будет частичный резерв: запустить задание можно только после дорезервирования.' : undefined,
    state,
    rows: p.components.map((r) => {
      const deficit = Number(r.shortage)
      return {
        level: levelByQty(Number(r.required), Number(r.free_now)),
        material: r.material,
        need: Number(r.required),
        free: Number(r.free_now),
        deficit: deficit > 0 ? deficit : undefined,
        unit: r.unit,
      }
    }),
  }
}

// Модель ссылается на свои файлы как sandbox:/mnt/data/имя или /mnt/data/имя. Такой адрес браузеру
// не открыть, поэтому ссылку превращаем в скачивание файла из чата, а картинку не дублируем.
const isSandbox = (url: string) => url.startsWith('sandbox:') || url.startsWith('/mnt/data/')
const keepSandboxUrls = (url: string) => (isSandbox(url) ? url : defaultUrlTransform(url))

function markdownComponents(files: ChatFile[]): Components {
  return {
    a: ({ href = '', children }) => {
      if (!isSandbox(href))
        return (
          <a href={href} target="_blank" rel="noreferrer">
            {children}
          </a>
        )
      const file = files.find((f) => href.endsWith(`/${f.filename}`))
      return file ? (
        <button
          className="text-accent hover:underline"
          onClick={() => downloadFile(`/api/chat/files/${file.id}`, file.filename)}
        >
          {children}
        </button>
      ) : (
        <span>{children}</span>
      )
    },
    img: ({ src = '', alt }) => (isSandbox(src) ? null : <img src={src} alt={alt} />),
  }
}

/** 18–20 — Ассистент: колонка диалогов, лента со стримингом ответа, поле ввода внизу. */
export default function AssistantPage() {
  const { conversationId } = useParams()
  const navigate = useNavigate()
  const convId = conversationId ? Number(conversationId) : null
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [streaming, setStreaming] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [confirming, setConfirming] = useState<number | null>(null)
  const [previews, setPreviews] = useState<Record<number, string>>({})
  const abortRef = useRef<AbortController | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)
  // Диалог, который мы только что создали сами при отправке: его сообщения уже на экране.
  const justCreated = useRef<number | null>(null)
  const requestedPreviews = useRef(new Set<number>())
  const previewUrls = useRef<string[]>([])

  const loadConversations = useCallback(() => {
    api<Conversation[]>('/api/chat/conversations')
      .then(setConversations)
      .catch((e) => setError(e.message))
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

  // Картинки отдаются только с токеном — загружаем их как blob и показываем через object URL.
  useEffect(() => {
    for (const m of messages) {
      for (const f of m.files) {
        if (!f.mime.startsWith('image/') || requestedPreviews.current.has(f.id)) continue
        requestedPreviews.current.add(f.id)
        fetchBlobUrl(`/api/chat/files/${f.id}`)
          .then((url) => {
            previewUrls.current.push(url)
            setPreviews((p) => ({ ...p, [f.id]: url }))
          })
          .catch(() => requestedPreviews.current.delete(f.id))
      }
    }
  }, [messages])
  useEffect(() => {
    const urls = previewUrls.current
    return () => urls.forEach((u) => URL.revokeObjectURL(u))
  }, [])

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
        if (e.status === 'start')
          patchLast((m) => ({ ...m, running_tools: [...(m.running_tools ?? []), e.name as string] }))
        else
          patchLast((m) => ({
            ...m,
            running_tools: (m.running_tools ?? []).filter((t) => t !== e.name),
            tool_calls: [
              ...m.tool_calls,
              { name: e.name as string, ok: e.status === 'ok', summary: e.summary as string, arguments: null },
            ],
          }))
        break
      case 'code':
        patchLast((m) => ({
          ...m,
          code: [...m.code, { code: e.code as string, logs: e.logs as string, error: Boolean(e.error) }],
        }))
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

  async function uploadFile(id: number, file: File): Promise<ChatFile> {
    const form = new FormData()
    form.append('file', file)
    const resp = await fetch(`/api/chat/conversations/${id}/files`, {
      method: 'POST',
      headers: authHeaders(),
      body: form,
    })
    const body = await resp.json()
    if (!resp.ok) throw new Error(body.detail ?? 'Не удалось загрузить файл')
    return body as ChatFile
  }

  async function send(question: string, files: File[] = []) {
    const q = question.trim() || (files.length ? 'Посмотри загруженный файл.' : '')
    if (!q || streaming) return
    setError(null)
    let id: number
    let uploaded: ChatFile[]
    try {
      id = await ensureConversation()
      uploaded = await Promise.all(files.map((f) => uploadFile(id, f)))
    } catch (e) {
      setError((e as Error).message)
      return
    }
    setMessages((ms) => [
      ...ms,
      { id: -1, role: 'user', content: q, status: 'complete', model: null, tool_calls: [], code: [], files: uploaded, actions: [], error: null },
      { id: -2, role: 'assistant', content: '', status: 'streaming', model: null, tool_calls: [], code: [], files: [], actions: [], error: null, running_tools: [] },
    ])
    const controller = new AbortController()
    abortRef.current = controller
    setStreaming(true)
    try {
      await postStream(
        `/api/chat/conversations/${id}/messages`,
        { text: q, file_ids: uploaded.map((f) => f.id) },
        onEvent,
        controller.signal,
      )
    } catch (e) {
      if ((e as Error).name !== 'AbortError') {
        setError((e as Error).message)
        // Сервер отказал до начала ответа — убираем черновые сообщения (у них отрицательные id).
        setMessages((ms) => ms.filter((m) => m.id > 0))
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

  async function decide(action: ChatAction, decision: 'confirm' | 'reject') {
    setConfirming(action.id)
    try {
      await api(`/api/chat/actions/${action.id}/${decision}`, { method: 'POST' })
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setConfirming(null)
    }
    if (convId) loadMessages(convId)
  }

  async function removeConversation(id: string) {
    try {
      await api(`/api/chat/conversations/${id}`, { method: 'DELETE' })
    } catch (e) {
      setError((e as Error).message)
    }
    loadConversations()
    if (Number(id) === convId) navigate('/assistant')
  }

  const asUiFile = (f: ChatFile): UiFile => ({
    kind: fileKind(f.filename, f.mime),
    name: f.filename,
    url: previews[f.id],
    onDownload: () => downloadFile(`/api/chat/files/${f.id}`, f.filename),
  })

  return (
    <div className="flex h-screen min-w-0 flex-1">
      <ConversationList
        items={conversations.map((c) => ({ id: String(c.id), title: c.title, group: dayGroup(c.updated_at) }))}
        activeId={convId ? String(convId) : undefined}
        onSelect={(id) => navigate(`/assistant/${id}`)}
        onNew={() => navigate('/assistant')}
        onDelete={removeConversation}
      />

      <section aria-label="Диалог" className="flex h-screen min-w-0 flex-1 flex-col">
        {messages.length === 0 ? (
          <ChatEmpty onPick={(text) => send(text)} />
        ) : (
          <div className="flex-1 overflow-y-auto px-8 pb-8 pt-7">
            <div className="mx-auto flex max-w-chat flex-col gap-7">
              {messages.map((m, i) => {
                const key = `${m.id}-${i}`
                if (m.role === 'user') return <UserMessage key={key} text={m.content} files={m.files.map(asUiFile)} />
                if (m.system_note)
                  return (
                    <div key={key} className="flex items-center gap-2 self-center text-xs text-fg-muted">
                      <CircleCheck className="size-3.5 text-fg-subtle" aria-hidden />
                      {m.content}
                    </div>
                  )
                const status = responseStatus(m)
                const hasAttachments = m.files.length + m.actions.length + m.code.length > 0
                return (
                  <AssistantMessage
                    key={key}
                    status={status}
                    attachments={
                      hasAttachments ? (
                        <>
                          {m.files.map((f) => (
                            <AssistantFile key={f.id} file={asUiFile(f)} />
                          ))}
                          {m.actions.map((a) => (
                            <ConfirmActionCard
                              key={a.id}
                              action={toConfirmAction(a, confirming === a.id)}
                              onConfirm={() => decide(a, 'confirm')}
                              onReject={() => decide(a, 'reject')}
                            />
                          ))}
                          {m.code.map((c, j) => (
                            <CodeRunBlock key={j} index={j + 1} run={{ code: c.code, output: c.logs || undefined }} />
                          ))}
                        </>
                      ) : undefined
                    }
                    footer={
                      m.model && status.kind !== 'thinking' ? (
                        <MessageFooter
                          model={m.model}
                          fallback={m.fallback_used}
                          tools={m.tool_calls.map((t) => ({ name: t.name, ok: t.ok, detail: t.summary }))}
                          codeRuns={m.code.length}
                        />
                      ) : undefined
                    }
                  >
                    {m.content ? (
                      <ReactMarkdown
                        remarkPlugins={[remarkGfm]}
                        urlTransform={keepSandboxUrls}
                        components={markdownComponents(m.files)}
                      >
                        {m.content}
                      </ReactMarkdown>
                    ) : undefined}
                  </AssistantMessage>
                )
              })}
              <div ref={bottomRef} />
            </div>
          </div>
        )}

        {error && (
          <div className="px-8 pb-1">
            <Banner tone="error" className="mx-auto max-w-chat" onDismiss={() => setError(null)}>
              {error}
            </Banner>
          </div>
        )}
        <Composer responding={streaming} onSend={(text, files) => send(text, files)} onStop={stop} />
      </section>
    </div>
  )
}
