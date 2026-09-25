import { useEffect, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useEventStream } from '@/shared/hooks/useEventStream'
import { queryKeys } from '@/shared/http/api'
import { applyRestoreEvent, initialProgress, type RestoreProgressEvent } from '@/shared/operations/restoreProgress'

export function useRestoreRequest() {
  const client = useQueryClient()
  const [request, setRequest] = useState<{ url: string; body?: unknown } | null>(null)
  const [state, setState] = useState(initialProgress)
  const syncOperations = () => { void client.invalidateQueries({ queryKey: queryKeys.operations.all }) }
  const stream = useEventStream<RestoreProgressEvent>({
    enabled: !!request && !state.error && !state.done,
    url: request?.url ?? '',
    body: request?.body,
    onResponse: syncOperations,
    onEvent: event => setState(previous => applyRestoreEvent(previous, event)),
    onClose: () => {
      syncOperations()
      setState(previous => previous.done || previous.error ? previous : { ...previous, active: false, error: '连接中断' })
    },
    onError: message => {
      syncOperations()
      setState(previous => ({ ...previous, active: false, error: message }))
    },
  })
  useEffect(() => {
    if (state.done || state.error) void client.invalidateQueries({ queryKey: queryKeys.operations.all })
  }, [client, state.done, state.error])
  useEffect(() => () => { void client.invalidateQueries({ queryKey: queryKeys.operations.all }) }, [client])
  const start = (next: { url: string; body?: unknown }) => {
    setState({ ...initialProgress, active: true, message: '准备开始' })
    setRequest(structuredClone(next))
  }
  const reset = () => { stream.abort(); setRequest(null); setState(initialProgress) }
  return { state, start, reset }
}
