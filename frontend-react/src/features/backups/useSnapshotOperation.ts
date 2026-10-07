import { useEffect, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { queryKeys } from '@/shared/http/api'
import { taskQueryKeys, useTask } from '@/features/tasks/queries';
import { snapshotApi } from './api'
import { useActiveRestorations } from './queries'
import type { RestoreProgressState, SnapshotScope, SnapshotTaskAccepted } from './contracts'

function scopeKey(scope: SnapshotScope | null): string {
  if (!scope || scope.kind === 'global') return scope?.kind ?? ''
  if (scope.kind === 'server') return JSON.stringify([scope.kind, scope.server_id])
  if (scope.kind === 'paths') return JSON.stringify([scope.kind, scope.server_id, [...new Set(scope.paths)].sort()])
  const selection = scope.selection
  return JSON.stringify([scope.kind, scope.server_id, selection.type, selection.region_dir_relpath ?? null,
    (selection.regions ?? []).map(pair => pair.join(',')).sort(), (selection.chunks ?? []).map(pair => pair.join(',')).sort()])
}

export function useSnapshotOperation(scope: SnapshotScope | null, options: {
  serverId?: string
  resumeAny?: boolean
  enabled?: boolean
} = {}) {
  const client = useQueryClient()
  const enabled = options.enabled ?? true
  const serverId = options.serverId ?? (scope && 'server_id' in scope ? scope.server_id : undefined)
  const discovery = useActiveRestorations(serverId, enabled)
  const [observedId, setObservedId] = useState<string | null>(null)
  const dismissed = useRef(new Set<string>())
  const [accepted, setAccepted] = useState<SnapshotTaskAccepted | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const submittingRef = useRef(false)
  const pending = discovery.data?.restorations.find(row => row.operation_id &&
    !dismissed.current.has(row.operation_id) && (options.resumeAny || scopeKey(row.scope) === scopeKey(scope)))
  const taskId = accepted?.task_id ?? observedId ?? pending?.operation_id ?? ''
  useEffect(() => { if (taskId) setObservedId(taskId) }, [taskId])
  const task = useTask(taskId)
  const terminal = task.data && ['completed', 'failed', 'cancelled'].includes(task.data.status)
  useEffect(() => { if (terminal) submittingRef.current = false }, [terminal])
  const checking = discovery.checking
  const state: RestoreProgressState = {
    active: submitting || (!!taskId && !terminal),
    percent: task.data?.progress ?? null,
    taskId,
    message: task.isError ? '暂时无法获取任务状态，正在重新连接' : task.data?.message || '正在准备任务',
    done: task.data?.status === 'completed',
    error: error ?? (terminal && task.data?.status !== 'completed' ? task.data?.error || task.data?.message || '恢复未完成' : null),
    log: accepted?.skipped_paths.length || (Array.isArray(task.data?.result?.skipped_paths) && task.data.result.skipped_paths.length) ? ['所选范围中的忽略目录将保持不变'] : [],
  }

  const busy = state.active || checking

  const submit = async (request: () => Promise<SnapshotTaskAccepted>) => {
    if (submittingRef.current || busy) return
    submittingRef.current = true
    if (taskId) dismissed.current.add(taskId)
    setAccepted(null)
    setObservedId(null)
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
    busy,
    checking,
    observationMessage: checking ? discovery.isError
      ? '暂时无法确认恢复任务状态，正在重新连接' : '正在检查恢复任务' : null,
    start: (sourceSnapshotId: string, previewId?: string) => scope ? submit(() => snapshotApi.restore({ source_snapshot_id: sourceSnapshotId, preview_id: previewId, scope: structuredClone(scope), entry_point: scope.kind === 'world' ? 'world' : 'files' })) : Promise.resolve(),
    rollback: (id: string) => submit(() => snapshotApi.rollback(id)),
    reset: () => {
      if (state.active) return
      if (taskId) dismissed.current.add(taskId)
      setAccepted(null)
      setObservedId(null)
      setError(null)
    },
  }
}
