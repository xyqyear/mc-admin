import { useEffect, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { queryKeys } from '@/shared/http/api'
import { useTaskQueries, taskQueryKeys } from '@/features/tasks/queries'
import { snapshotApi } from './api'
import { useRestorationHistory } from './queries'
import type { RestoreProgressState, SnapshotScope, SnapshotTaskAccepted } from './contracts'

function scopeKey(scope: SnapshotScope | null): string {
  if (!scope || scope.kind === 'global') return scope?.kind ?? ''
  if (scope.kind === 'server') return JSON.stringify([scope.kind, scope.server_id])
  if (scope.kind === 'paths') return JSON.stringify([scope.kind, scope.server_id, [...new Set(scope.paths)].sort()])
  const selection = scope.selection
  return JSON.stringify([scope.kind, scope.server_id, selection.type, selection.region_dir_relpath ?? null,
    (selection.regions ?? []).map(pair => pair.join(',')).sort(), (selection.chunks ?? []).map(pair => pair.join(',')).sort()])
}

export function useSnapshotOperation(scope: SnapshotScope | null, resumeAny = false) {
  const client = useQueryClient()
  const history = useRestorationHistory(scope && 'server_id' in scope ? scope.server_id : undefined, 0, !!scope)
  const [accepted, setAccepted] = useState<SnapshotTaskAccepted | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const submittingRef = useRef(false)
  const pending = history.data?.restorations.find(row =>
    (row.status === 'pending' || row.status === 'running') && (resumeAny || scopeKey(row.scope) === scopeKey(scope)))
  const taskId = accepted?.task_id ?? pending?.operation_id ?? ''
  const task = useTaskQueries().useTask(taskId)
  const terminal = task.data && ['completed', 'failed', 'cancelled'].includes(task.data.status)
  useEffect(() => { if (terminal) submittingRef.current = false }, [terminal])
  const state: RestoreProgressState = {
    active: submitting || (!!taskId && !terminal),
    percent: task.data?.progress ?? 0,
    message: task.isError ? '暂时无法获取任务状态，正在重新连接' : task.data?.message || '正在准备任务',
    done: task.data?.status === 'completed',
    error: error ?? (terminal && task.data?.status !== 'completed' ? task.data?.error || task.data?.message || '恢复未完成' : null),
    log: accepted?.skipped_paths.length || (Array.isArray(task.data?.result?.skipped_paths) && task.data.result.skipped_paths.length) ? ['所选范围中的忽略目录将保持不变'] : [],
  }

  const submit = async (request: () => Promise<SnapshotTaskAccepted>) => {
    if (submittingRef.current || state.active) return
    submittingRef.current = true
    setSubmitting(true)
    setError(null)
    try {
      setAccepted(await request())
      void client.invalidateQueries({ queryKey: taskQueryKeys.all })
      void client.invalidateQueries({ queryKey: queryKeys.operations.all })
      void client.invalidateQueries({ queryKey: queryKeys.snapshots.all })
    } catch (failure) {
      submittingRef.current = false
      setError(failure instanceof Error ? failure.message : '无法提交恢复任务')
    } finally {
      setSubmitting(false)
    }
  }

  return {
    state,
    taskId,
    history,
    start: (sourceSnapshotId: string, previewId?: string) => scope ? submit(() => snapshotApi.restore({ source_snapshot_id: sourceSnapshotId, preview_id: previewId, scope: structuredClone(scope), entry_point: scope.kind === 'world' ? 'world' : 'files' })) : Promise.resolve(),
    rollback: (id: string) => submit(() => snapshotApi.rollback(id)),
    reset: () => { if (!state.active) { setAccepted(null); setError(null) } },
  }
}
