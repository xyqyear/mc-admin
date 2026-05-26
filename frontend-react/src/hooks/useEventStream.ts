import { useEffect, useRef } from 'react'

import { readEventStream } from '@/utils/eventStream'

export interface UseEventStreamOptions<TEvent> {
  enabled: boolean
  url: string
  method?: 'GET' | 'POST'
  body?: unknown
  onEvent: (event: TEvent) => void
  onClose?: () => void
  onError?: (message: string) => void
  onResponse?: (res: Response) => void
}

export interface UseEventStreamHandle {
  abort: () => void
}

export function useEventStream<TEvent>(
  opts: UseEventStreamOptions<TEvent>,
): UseEventStreamHandle {
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

    void readEventStream<TEvent>({
      url: opts.url,
      method: opts.method,
      body: opts.body,
      signal: ctrl.signal,
      onEvent: (event) => onEventRef.current(event),
      onClose: () => onCloseRef.current?.(),
      onError: (message) => onErrorRef.current?.(message),
      onResponse: (res) => onResponseRef.current?.(res),
    })

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
