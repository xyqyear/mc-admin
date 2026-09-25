import { useEventStream } from '@/shared/hooks/useEventStream'
import { getErrorMessage, getErrorStatus } from '@/shared/http/api'
import { useEffect, useRef, useState } from 'react'
import { useWorldRestoreMutations } from '@/features/world/restore/commands'
import type { RestorePreviewRequest } from '@/features/world/restore/contracts'
import type { PreviewEvent } from '@/features/world/restore/contracts'

interface PreviewState {
  percent: number
  message: string
  sessionId: string | null
  ready: boolean
  error: string | null
}

const initialState: PreviewState = {
  percent: 0,
  message: '准备开始',
  sessionId: null,
  ready: false,
  error: null,
}

const STAGE_LABEL: Record<string, string> = {
  start: '准备',
  stage: '提取快照内容',
  merge_region: '合并区块',
  render_progress: '渲染',
  ready: '就绪',
  error: '错误',
}

// 30s heartbeat — well under the backend's 30-min TTL.
const HEARTBEAT_MS = 30_000

export function useRestorePreview(serverId: string, request: RestorePreviewRequest | null) {
  const [state, setState] = useState<PreviewState>(initialState)
  const sessionRef = useRef<string | null>(null)
  const { useEndPreview, useHeartbeatPreview } = useWorldRestoreMutations()
  const endPreview = useEndPreview(serverId)
  const heartbeat = useHeartbeatPreview(serverId)
  // Object identity is the trigger; callers create a new request on each open.
  useEffect(() => {
    if (!request) return
    setState(initialState)
  }, [request])

  useEventStream<PreviewEvent>({
    enabled: !!request && !state.error,
    url: `/servers/${serverId}/world-restore/preview`,
    method: 'POST',
    body: request
      ? {
        source_snapshot_id: request.sourceSnapshotId,
        selection: request.selection,
      }
      : undefined,
    onEvent: (ev) => {
      const stageText = STAGE_LABEL[ev.event_type] ?? ev.event_type
      const text = ev.message ?? stageText
      if (ev.session_id) sessionRef.current = ev.session_id
      if (ev.event_type === 'error') {
        setState((prev) => ({ ...prev, error: ev.message ?? '未知错误' }))
        return
      }
      if (ev.event_type === 'ready') {
        setState((prev) => ({
          ...prev,
          percent: 100,
          message: text,
          ready: true,
          sessionId: ev.session_id ?? prev.sessionId,
        }))
        return
      }
      setState((prev) => ({
        ...prev,
        percent: ev.percent ?? prev.percent,
        message: text,
        sessionId: ev.session_id ?? prev.sessionId,
      }))
    },
    onError: (msg) => setState((prev) => ({ ...prev, error: msg })),
    onClose: () => setState((prev) => prev.ready || prev.error
      ? prev
      : { ...prev, error: '连接中断，请重新生成预览' }),
  })

  const endRef = useRef(endPreview.mutate)
  endRef.current = endPreview.mutate
  const heartbeatRef = useRef(heartbeat.mutate)
  heartbeatRef.current = heartbeat.mutate
  useEffect(() => {
    if (!request) return
    return () => {
      const sessionId = sessionRef.current
      sessionRef.current = null
      if (sessionId) endRef.current(sessionId)
    }
  }, [request, serverId])
  useEffect(() => {
    if (!request || !state.sessionId || state.error) return
    const sessionId = state.sessionId
    const timer = window.setInterval(() => heartbeatRef.current(sessionId, {
      onError: error => {
        const status = getErrorStatus(error)
        if (status !== 404 && status !== 409 && status !== 410) return
        setState(previous => ({ ...previous, ready: false, error: `${getErrorMessage(error, '预览已失效')}，请关闭后重新生成预览` }))
      },
    }), HEARTBEAT_MS)
    return () => window.clearInterval(timer)
  }, [request, state.sessionId, state.error])
  return state
}
