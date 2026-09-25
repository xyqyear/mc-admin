export type BackgroundTaskStatus = 'pending' | 'running' | 'completed' | 'failed' | 'cancelled'

export type BackgroundTaskType =
  | 'archive_create'
  | 'archive_extract'
  | 'file_ownership_repair'
  | 'server_rebuild'
  | 'world_restore'
  | 'chunk_prune_preview'
  | 'chunk_prune_apply'

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
