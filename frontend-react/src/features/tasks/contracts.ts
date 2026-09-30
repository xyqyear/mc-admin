export type BackgroundTaskStatus = 'pending' | 'running' | 'completed' | 'failed' | 'cancelled'

export type BackgroundTaskType =
  | 'server_start' | 'server_up' | 'server_restart' | 'server_stop' | 'server_down'
  | 'server_remove' | 'server_create' | 'server_sync'
  | 'file_delete' | 'archive_delete' | 'map_initialize' | 'self_check' | 'dns_update'
  | 'archive_hash' | 'archive_publish'
  | 'archive_create'
  | 'archive_extract'
  | 'file_ownership_repair'
  | 'server_rebuild'
  | 'world_restore'
  | 'snapshot_create' | 'snapshot_restore'
  | 'snapshot_preview' | 'snapshot_preview_cleanup' | 'snapshot_delete' | 'snapshot_unlock'
  | 'chunk_prune_preview'
  | 'chunk_prune_apply'

export interface TaskAccepted {
  task_id: string
}

export interface BackgroundTask {
  taskId: string
  taskType: BackgroundTaskType
  name: string
  status: BackgroundTaskStatus
  progress: number | null
  message: string
  serverId: string | null
  createdAt: number
  startedAt?: number
  endedAt?: number
  result?: Record<string, unknown>
  error?: string
  errorCode?: string
  cancellable: boolean
}

export interface BackgroundTaskResponse {
  task_id: string
  task_type: BackgroundTaskType
  name: string
  status: BackgroundTaskStatus
  progress: number | null
  message: string
  server_id: string | null
  created_at: string
  started_at?: string
  ended_at?: string
  result?: Record<string, unknown>
  error?: string
  error_code?: string
  cancellable: boolean
}

export interface BackgroundTaskListResponse {
  tasks: BackgroundTaskResponse[]
  total: number
}
