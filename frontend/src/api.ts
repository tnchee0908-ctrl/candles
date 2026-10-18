const TOKEN_KEY = 'candles_token'

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY)
  } catch {
    return null
  }
}

export function setToken(token: string | null) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token)
    else localStorage.removeItem(TOKEN_KEY)
  } catch {
    /* приватный режим браузера — живём без сохранения */
  }
}

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

export function authHeaders(): Record<string, string> {
  const token = getToken()
  return token ? { Authorization: `Bearer ${token}` } : {}
}

// Если ответ пришёл не от бэкенда (страница nginx, сервер перезапускается), показываем понятный текст.
const STATUS_TEXT: Record<number, string> = {
  413: 'Файл слишком большой: можно загрузить не больше 5 МБ.',
  429: 'Слишком много запросов. Подождите немного и повторите.',
  502: 'Сервер временно недоступен (перезапускается). Повторите через минуту.',
  503: 'Сервер временно недоступен. Повторите через минуту.',
  504: 'Сервер не ответил вовремя. Повторите через минуту.',
}

export async function parseError(resp: Response): Promise<ApiError> {
  let message = STATUS_TEXT[resp.status] ?? `Не удалось выполнить запрос (код ${resp.status}).`
  try {
    const body = await resp.json()
    if (typeof body.detail === 'string') message = body.detail
  } catch {
    /* не JSON — остаётся текст по коду ответа */
  }
  if (resp.status === 401) {
    setToken(null)
    window.dispatchEvent(new Event('candles:logout'))
  }
  return new ApiError(resp.status, message)
}

/** fetch с понятной ошибкой, если сети нет совсем (вместо «Failed to fetch»). */
export async function request(path: string, init: RequestInit): Promise<Response> {
  try {
    return await fetch(path, init)
  } catch (e) {
    if ((e as Error).name === 'AbortError') throw e
    throw new ApiError(0, 'Нет связи с сервером. Проверьте подключение и повторите.')
  }
}

export async function api<T>(path: string, options: RequestInit & { json?: unknown } = {}): Promise<T> {
  const { json, headers, ...rest } = options
  const resp = await request(path, {
    ...rest,
    headers: {
      ...(json !== undefined ? { 'Content-Type': 'application/json' } : {}),
      ...authHeaders(),
      ...headers,
    },
    body: json !== undefined ? JSON.stringify(json) : rest.body,
  })
  if (!resp.ok) throw await parseError(resp)
  return (await resp.json()) as T
}

export async function fetchBlobUrl(path: string): Promise<string> {
  const resp = await request(path, { headers: authHeaders() })
  if (!resp.ok) throw await parseError(resp)
  return URL.createObjectURL(await resp.blob())
}

export async function downloadFile(path: string, filename: string) {
  const url = await fetchBlobUrl(path)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  setTimeout(() => URL.revokeObjectURL(url), 10_000)
}

export type SseEvent = { type: string; [key: string]: unknown }

/** POST с ответом в виде Server-Sent Events. Возвращает функцию, которая обрывает поток. */
export async function postStream(
  path: string,
  body: unknown,
  onEvent: (event: SseEvent) => void,
  signal: AbortSignal,
): Promise<void> {
  const resp = await request(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify(body),
    signal,
  })
  if (!resp.ok || !resp.body) throw await parseError(resp)
  const reader = resp.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    let sep: number
    while ((sep = buffer.indexOf('\n\n')) >= 0) {
      const block = buffer.slice(0, sep)
      buffer = buffer.slice(sep + 2)
      const data = block
        .split('\n')
        .filter((l) => l.startsWith('data: '))
        .map((l) => l.slice(6))
        .join('\n')
      if (data) onEvent(JSON.parse(data) as SseEvent)
    }
  }
}
