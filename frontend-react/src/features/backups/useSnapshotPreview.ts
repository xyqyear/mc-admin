import { useEffect, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { waitForTaskResult, useCancelTask } from '@/features/tasks/commands';
import { getErrorMessage, getErrorStatus } from '@/shared/http/api'
import { snapshotApi } from './api'
import type { SnapshotPreviewRequest, SnapshotPreviewResult } from './contracts'

interface PreviewState {
  active: boolean
  taskId: string | null
  result: SnapshotPreviewResult | null
  progress: number | null
  message: string
  error: string | null
}
const initial: PreviewState = { active: false, taskId: null, result: null, progress: null, message: '正在准备预览', error: null }

export function useSnapshotPreview(request: SnapshotPreviewRequest | null) {
  const client = useQueryClient()
  const [state, setState] = useState<PreviewState>(initial)
  const cancel = useCancelTask()
  const readyId = useRef<string | null>(null)

  useEffect(() => {
    if (!request) return
    const observation = new AbortController()
    setState({ ...initial, active: true })
    readyId.current = null
    const timer = setTimeout(() => {
      void (async () => {
        try {
          const accepted = await snapshotApi.preparePreview(request)
          if (observation.signal.aborted) return
          setState(previous => ({ ...previous, taskId: accepted.task_id }))
          const result = await waitForTaskResult<SnapshotPreviewResult>(client, accepted, {
            signal: observation.signal,
            onProgress: task => setState(previous => ({ ...previous, message: task.message || '正在准备预览', progress: task.progress })),
          })
          if (observation.signal.aborted) return
          readyId.current = result.preview_id
          setState(previous => ({ ...previous, active: false, result, progress: 100, message: '预览已就绪' }))
        } catch (error) {
          if (!observation.signal.aborted) setState(previous => ({ ...previous, active: false, error: getErrorMessage(error, '预览准备失败') }))
        }
      })()
    }, 0)
    return () => {
      clearTimeout(timer)
      observation.abort()
      const id = readyId.current
      readyId.current = null
      if (id) void snapshotApi.closePreview(id)
        .then(accepted => waitForTaskResult(client, accepted))
        .catch(() => toast.message('预览清理未完成，系统会继续按有效期回收'))
    }
  }, [client, request])

  useEffect(() => {
    const id = state.result?.preview_id
    if (!request || !id || state.error) return
    const timer = setInterval(() => {
      void snapshotApi.heartbeatPreview(id).catch(error => {
        const status = getErrorStatus(error)
        if (status === 404 || status === 409 || status === 410) {
          setState(previous => ({ ...previous, result: null, error: '预览已失效，请关闭后重新生成' }))
        }
      })
    }, 30_000)
    return () => clearInterval(timer)
  }, [request, state.result?.preview_id, state.error])

  const stop = async () => {
    if (!state.taskId) return
    try {
      await cancel.mutateAsync(state.taskId)
    } catch (error) {
      toast.error(getErrorMessage(error, '无法停止预览准备，请重试'))
    }
  }
  return { ...state, cancel: stop, cancelling: cancel.isPending }
}
