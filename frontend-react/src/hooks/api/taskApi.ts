import type {
  BackgroundTask,
  BackgroundTaskStatus,
  BackgroundTaskType,
} from '@/stores/useBackgroundTaskStore'
import api from '@/utils/api'

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
  cancellable: boolean
}

export interface BackgroundTaskListResponse {
  tasks: BackgroundTaskResponse[]
  total: number
}

const transformTask = (task: BackgroundTaskResponse): BackgroundTask => ({
  taskId: task.task_id,
  taskType: task.task_type,
  name: task.name,
  status: task.status,
  progress: task.progress,
  message: task.message,
  serverId: task.server_id,
  createdAt: new Date(task.created_at).getTime(),
  startedAt: task.started_at ? new Date(task.started_at).getTime() : undefined,
  endedAt: task.ended_at ? new Date(task.ended_at).getTime() : undefined,
  result: task.result,
  error: task.error,
  cancellable: task.cancellable,
})

export const taskApi = {
  getTasks: async (params?: {
    status?: BackgroundTaskStatus
    server_id?: string
    limit?: number
    offset?: number
  }): Promise<{ tasks: BackgroundTask[]; total: number }> => {
    const response = await api.get<BackgroundTaskListResponse>('/tasks', {
      params,
    })
    return {
      tasks: response.data.tasks.map(transformTask),
      total: response.data.total,
    }
  },

  getActiveTasks: async (): Promise<BackgroundTask[]> => {
    const response = await api.get<BackgroundTaskListResponse>('/tasks', {
      params: { active_only: true },
    })
    return response.data.tasks.map(transformTask)
  },

  getTask: async (taskId: string): Promise<BackgroundTask> => {
    const response = await api.get<BackgroundTaskResponse>(`/tasks/${taskId}`)
    return transformTask(response.data)
  },

  cancelTask: async (taskId: string): Promise<void> => {
    await api.post(`/tasks/${taskId}/cancel`)
  },

  deleteTask: async (taskId: string): Promise<void> => {
    await api.delete(`/tasks/${taskId}`)
  },

  clearCompletedTasks: async (): Promise<void> => {
    await api.delete('/tasks', { params: { completed_only: true } })
  },
}
