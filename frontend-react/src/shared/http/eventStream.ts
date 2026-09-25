import { buildApiUrl, CSRF_HEADER_NAME, getCsrfToken, createApiError, type ApiError } from '@/shared/http/api'

export interface EventStreamOptions<TEvent> {
  url: string
  method?: 'GET' | 'POST'
  body?: unknown
  signal?: AbortSignal
  onEvent: (event: TEvent) => void
  onClose?: () => void
  onError?: (message: string, error?: ApiError) => void
  onResponse?: (res: Response) => void
}

const PROTOCOL_RE = /^https?:\/\//i

export const buildEventStreamUrl = (input: string): string => {
  if (PROTOCOL_RE.test(input)) return input
  return buildApiUrl(input)
}

export async function readEventStream<TEvent>(
  opts: EventStreamOptions<TEvent>,
): Promise<void> {
  let reader: ReadableStreamDefaultReader<Uint8Array> | undefined
  try {
    const headers: Record<string, string> = {
      Accept: 'text/event-stream',
    }
    if (opts.body !== undefined) headers['Content-Type'] = 'application/json'
    const csrfToken = getCsrfToken()
    if (csrfToken && (opts.method ?? 'POST') !== 'GET') {
      headers[CSRF_HEADER_NAME] = csrfToken
    }

    const res = await fetch(buildEventStreamUrl(opts.url), {
      method: opts.method ?? 'POST',
      headers,
      body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
      signal: opts.signal,
      credentials: 'same-origin',
    })
    opts.onResponse?.(res)
    if (!res.ok || !res.body) {
      let data: unknown
      try { data = await res.json() } catch { /* The response may have no JSON body. */ }
      throw createApiError(data, res.status, undefined, `HTTP ${res.status}`)
    }

    reader = res.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    while (true) {
      const { value, done } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      let idx: number
      while ((idx = buffer.indexOf('\n\n')) !== -1) {
        const block = buffer.slice(0, idx)
        buffer = buffer.slice(idx + 2)
        const dataLines = block
          .split('\n')
          .filter((l) => l.startsWith('data:'))
          .map((l) => l.slice(5).trim())
        if (dataLines.length === 0) continue
        const payload = dataLines.join('\n')
        try {
          opts.onEvent(JSON.parse(payload) as TEvent)
        } catch {
          // Ignore malformed events and keep the stream open.
        }
      }
    }
    if (!opts.signal?.aborted) opts.onClose?.()
  } catch (e) {
    if (opts.signal?.aborted || (e as { name?: string })?.name === 'AbortError') return
    const error = (e as ApiError)?.name === 'ApiError' ? e as ApiError : createApiError(undefined, undefined, undefined, (e as Error).message ?? '连接失败')
    opts.onError?.(error.message, error)
  } finally {
    if (reader) {
      try { await reader.cancel() } catch { /* An aborted fetch already closed the stream. */ }
      reader.releaseLock()
    }
  }
}
