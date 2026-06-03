import { buildApiUrl, CSRF_HEADER_NAME, getCsrfToken } from '@/utils/api'

export interface EventStreamOptions<TEvent> {
  url: string
  method?: 'GET' | 'POST'
  body?: unknown
  signal?: AbortSignal
  onEvent: (event: TEvent) => void
  onClose?: () => void
  onError?: (message: string) => void
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
      let detail = `HTTP ${res.status}`
      try {
        const data = await res.json()
        if (data && typeof data === 'object' && 'detail' in data) {
          detail = typeof data.detail === 'string'
            ? data.detail
            : JSON.stringify(data.detail)
        }
      } catch {
        // Keep the generic HTTP detail.
      }
      throw new Error(detail)
    }

    const reader = res.body.getReader()
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
    opts.onClose?.()
  } catch (e) {
    if ((e as { name?: string })?.name === 'AbortError') return
    opts.onError?.((e as Error).message ?? 'stream error')
  }
}
