import api from '@/utils/api'
import type {
  BackgroundTask,
  BackgroundTaskStatus,
  BackgroundTaskType,
} from '@/stores/useBackgroundTaskStore'

export interface BackgroundTaskResponse {
  task_id: string
  task_type: BackgroundTaskType
  status: BackgroundTaskStatus
  progress: number
  message: string
  server_id?: string
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

// Mock data for development - will be replaced with real API calls
const MOCK_ENABLED = true

const mockTasks: BackgroundTaskResponse[] = [
  {
    task_id: 'mock_task_1',
    task_type: 'archive_create',
    status: 'running',
    progress: 65,
    message: '正在压缩: world/region/r.0.0.mca',
    server_id: 'survival',
    created_at: new Date(Date.now() - 120000).toISOString(),
    started_at: new Date(Date.now() - 100000).toISOString(),
    cancellable: true,
  },
  {
    task_id: 'mock_task_2',
    task_type: 'snapshot_create',
    status: 'running',
    progress: 30,
    message: '正在备份: plugins/',
    server_id: 'creative',
    created_at: new Date(Date.now() - 60000).toISOString(),
    started_at: new Date(Date.now() - 50000).toISOString(),
    cancellable: true,
  },
  {
    task_id: 'mock_task_3',
    task_type: 'server_start',
    status: 'completed',
    progress: 100,
    message: '服务器启动完成',
    server_id: 'lobby',
    created_at: new Date(Date.now() - 300000).toISOString(),
    started_at: new Date(Date.now() - 290000).toISOString(),
    ended_at: new Date(Date.now() - 180000).toISOString(),
    cancellable: false,
  },
  {
    task_id: 'mock_task_4',
    task_type: 'archive_create',
    status: 'failed',
    progress: 45,
    message: '压缩失败',
    server_id: 'minigames',
    created_at: new Date(Date.now() - 600000).toISOString(),
    started_at: new Date(Date.now() - 590000).toISOString(),
    ended_at: new Date(Date.now() - 500000).toISOString(),
    error: '磁盘空间不足',
    cancellable: true,
  },
]

// Simulate progress updates for running tasks
let mockProgressCounter = 0
const getMockTasksWithProgress = (): BackgroundTaskResponse[] => {
  mockProgressCounter++
  return mockTasks.map((task) => {
    if (task.status === 'running') {
      const newProgress = Math.min(
        99,
        task.progress + (mockProgressCounter % 5 === 0 ? 1 : 0)
      )
      return { ...task, progress: newProgress }
    }
    return task
  })
}

export const taskApi = {
  // Get all tasks with optional filtering
  getTasks: async (params?: {
    status?: BackgroundTaskStatus
    server_id?: string
    limit?: number
    offset?: number
  }): Promise<{ tasks: BackgroundTask[]; total: number }> => {
    if (MOCK_ENABLED) {
      let tasks = getMockTasksWithProgress()
      if (params?.status) {
        tasks = tasks.filter((t) => t.status === params.status)
      }
      if (params?.server_id) {
        tasks = tasks.filter((t) => t.server_id === params.server_id)
      }
      return {
        tasks: tasks.map(transformTask),
        total: tasks.length,
      }
    }

    const response = await api.get<BackgroundTaskListResponse>('/tasks', {
      params,
    })
    return {
      tasks: response.data.tasks.map(transformTask),
      total: response.data.total,
    }
  },

  // Get active tasks (pending + running)
  getActiveTasks: async (): Promise<BackgroundTask[]> => {
    if (MOCK_ENABLED) {
      const tasks = getMockTasksWithProgress()
      return tasks
        .filter((t) => t.status === 'pending' || t.status === 'running')
        .map(transformTask)
    }

    const response = await api.get<BackgroundTaskListResponse>('/tasks', {
      params: { active_only: true },
    })
    return response.data.tasks.map(transformTask)
  },

  // Get single task by ID
  getTask: async (taskId: string): Promise<BackgroundTask> => {
    if (MOCK_ENABLED) {
      const task = getMockTasksWithProgress().find((t) => t.task_id === taskId)
      if (!task) {
        throw new Error('Task not found')
      }
      return transformTask(task)
    }

    const response = await api.get<BackgroundTaskResponse>(`/tasks/${taskId}`)
    return transformTask(response.data)
  },

  // Cancel a task
  cancelTask: async (taskId: string): Promise<void> => {
    if (MOCK_ENABLED) {
      console.log('[Mock] Cancelling task:', taskId)
      return
    }

    await api.post(`/tasks/${taskId}/cancel`)
  },

  // Delete a completed/failed/cancelled task
  deleteTask: async (taskId: string): Promise<void> => {
    if (MOCK_ENABLED) {
      console.log('[Mock] Deleting task:', taskId)
      return
    }

    await api.delete(`/tasks/${taskId}`)
  },

  // Clear all completed tasks
  clearCompletedTasks: async (): Promise<void> => {
    if (MOCK_ENABLED) {
      console.log('[Mock] Clearing completed tasks')
      return
    }

    await api.delete('/tasks', { params: { completed_only: true } })
  },
}
