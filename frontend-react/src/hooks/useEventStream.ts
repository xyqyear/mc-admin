import { useEffect, useRef } from 'react'

import { getApiBaseUrl } from '@/utils/api'
import { useTokenStore } from '@/stores/useTokenStore'

// Reusable Server-Sent Events consumer.
//
// We can't use the browser's native EventSource because the backend requires
// JWT auth in the Authorization header — EventSource only supports cookie
// auth. So we drive the stream with fetch + a manual `data: <json>\n\n`
// parser.
//
// The hook is enabled-flag driven: flipping `enabled` from false → true opens
// the stream; flipping back to false aborts it. URL/body changes while
// enabled also restart the stream — pass stable references when that's not
// what you want.

export interface UseEventStreamOptions<TEvent> {
  enabled: boolean
  // Path under /api — e.g. `/servers/abc/world-restore/restore`. Absolute URLs
  // (with a leading "http") are also accepted for non-API streams.
  url: string
  method?: 'GET' | 'POST'
  body?: unknown
  onEvent: (event: TEvent) => void
  onClose?: () => void
  onError?: (message: string) => void
  // Optional: run when the response is received (status + headers). Useful for
  // surfacing 4xx/5xx errors before any SSE events arrive — the consumer can
  // throw or short-circuit by setting `enabled` to false.
  onResponse?: (res: Response) => void
}

export interface UseEventStreamHandle {
  abort: () => void
}

const PROTOCOL_RE = /^https?:\/\//i

const buildUrl = (input: string): string => {
  if (PROTOCOL_RE.test(input)) return input
  const base = getApiBaseUrl()
  return `${base}${input.startsWith('/') ? '' : '/'}${input}`
}

export function useEventStream<TEvent>(
  opts: UseEventStreamOptions<TEvent>,
): UseEventStreamHandle {
  // Latest-callback refs so the streaming loop doesn't restart whenever the
  // caller re-creates handler closures inline. Restarts are still triggered
  // by the values in the dependency array below.
  const onEventRef = useRef(opts.onEvent)
  const onCloseRef = useRef(opts.onClose)
  const onErrorRef = useRef(opts.onError)
  const onResponseRef = useRef(opts.onResponse)
  onEventRef.current = opts.onEvent
  onCloseRef.current = opts.onClose
  onErrorRef.current = opts.onError
  onResponseRef.current = opts.onResponse

  const abortRef = useRef<AbortController | null>(null)

  useEffect(() => {
    if (!opts.enabled) return

    const ctrl = new AbortController()
    abortRef.current = ctrl

    ;(async () => {
      try {
        const token = useTokenStore.getState().token
        const headers: Record<string, string> = {
          Accept: 'text/event-stream',
        }
        if (token) headers.Authorization = `Bearer ${token}`
        if (opts.body !== undefined) headers['Content-Type'] = 'application/json'

        const res = await fetch(buildUrl(opts.url), {
          method: opts.method ?? 'POST',
          headers,
          body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
          signal: ctrl.signal,
        })
        onResponseRef.current?.(res)
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
            // ignore — keep generic detail
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
            let event: TEvent
            try {
              event = JSON.parse(payload) as TEvent
            } catch {
              continue
            }
            onEventRef.current(event)
          }
        }
        onCloseRef.current?.()
      } catch (e) {
        if ((e as { name?: string })?.name === 'AbortError') return
        onErrorRef.current?.((e as Error).message ?? 'stream error')
      }
    })()

    return () => {
      ctrl.abort()
      abortRef.current = null
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [opts.enabled, opts.url, opts.method, JSON.stringify(opts.body ?? null)])

  return {
    abort: () => abortRef.current?.abort(),
  }
}
