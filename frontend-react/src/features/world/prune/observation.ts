import type { ChunkPrunePreview } from './contracts'

interface PruneObservation {
  preview: ChunkPrunePreview | null
  previewTaskId?: string
  applyTaskId?: string
}

function taskId(value: unknown): string | undefined | false {
  if (value === null) return undefined
  if (!value || typeof value !== 'object') return false
  const task = value as Record<string, unknown>
  return typeof task.task_id === 'string' && !!task.task_id ? task.task_id : false
}

function isPreview(value: unknown): value is ChunkPrunePreview {
  if (!value || typeof value !== 'object') return false
  const preview = value as Record<string, unknown>
  return typeof preview.task_id === 'string'
    && (preview.input_version === null || typeof preview.input_version === 'string')
    && (preview.expires_at === null || (typeof preview.expires_at === 'string' && Number.isFinite(Date.parse(preview.expires_at))))
    && ['building', 'ready', 'expired', 'stale', 'consumed', 'unavailable'].includes(String(preview.availability))
    && (preview.apply_task_id === null || typeof preview.apply_task_id === 'string')
}

export function pruneStateIndex(rows: unknown[] | undefined, serverId?: string): PruneObservation | undefined {
  if (!rows || !serverId) return undefined
  let current: PruneObservation = { preview: null }
  const servers = new Set<string>()
  for (const value of rows) {
    if (!value || typeof value !== 'object') return undefined
    const row = value as Record<string, unknown>
    if (typeof row.server_id !== 'string' || servers.has(row.server_id)) return undefined
    servers.add(row.server_id)
    const previewTaskId = taskId(row.preview_task)
    const applyTaskId = taskId(row.apply_task)
    if (previewTaskId === false || applyTaskId === false || (row.preview !== null && !isPreview(row.preview))) return undefined
    if (row.server_id === serverId) current = { preview: row.preview, previewTaskId, applyTaskId }
  }
  return current
}
