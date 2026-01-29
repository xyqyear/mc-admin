import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export type BackgroundTaskStatus = 'pending' | 'running' | 'completed' | 'failed' | 'cancelled'

export type BackgroundTaskType =
  | 'archive_create'
  | 'archive_extract'
  | 'snapshot_create'
  | 'snapshot_restore'
  | 'server_start'
  | 'server_stop'
  | 'server_restart'

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
  cancellable: boolean
}

interface BackgroundTaskState {
  tasks: BackgroundTask[]
  addTask: (task: Omit<BackgroundTask, 'createdAt'>) => void
  updateTask: (taskId: string, updates: Partial<BackgroundTask>) => void
  removeTask: (taskId: string) => void
  clearCompletedTasks: () => void
  getTask: (taskId: string) => BackgroundTask | undefined
  getActiveTasksCount: () => number
  getRunningTasks: () => BackgroundTask[]
  getPendingTasks: () => BackgroundTask[]
}

export const useBackgroundTaskStore = create<BackgroundTaskState>()(
  persist(
    (set, get) => ({
      tasks: [],

      addTask: (taskData) => {
        const newTask: BackgroundTask = {
          ...taskData,
          createdAt: Date.now(),
        }

        set((state) => ({
          tasks: [...state.tasks, newTask],
        }))
      },

      updateTask: (taskId, updates) => {
        set((state) => ({
          tasks: state.tasks.map((task) =>
            task.taskId === taskId ? { ...task, ...updates } : task
          ),
        }))
      },

      removeTask: (taskId) => {
        set((state) => ({
          tasks: state.tasks.filter((task) => task.taskId !== taskId),
        }))
      },

      clearCompletedTasks: () => {
        set((state) => ({
          tasks: state.tasks.filter(
            (task) => task.status === 'pending' || task.status === 'running'
          ),
        }))
      },

      getTask: (taskId) => {
        return get().tasks.find((task) => task.taskId === taskId)
      },

      getActiveTasksCount: () => {
        return get().tasks.filter(
          (task) => task.status === 'pending' || task.status === 'running'
        ).length
      },

      getRunningTasks: () => {
        return get().tasks.filter((task) => task.status === 'running')
      },

      getPendingTasks: () => {
        return get().tasks.filter((task) => task.status === 'pending')
      },
    }),
    {
      name: 'background-task-store',
      partialize: (state) => ({
        tasks: state.tasks.map((task) => ({
          ...task,
          // Convert running/pending to cancelled on app restart
          status:
            task.status === 'running' || task.status === 'pending'
              ? ('cancelled' as const)
              : task.status,
        })),
      }),
    }
  )
)

// Selector hooks for performance optimization
export const useBackgroundTasks = () =>
  useBackgroundTaskStore((state) => state.tasks)

export const useActiveBackgroundTasks = () =>
  useBackgroundTaskStore((state) =>
    state.tasks.filter(
      (task) => task.status === 'pending' || task.status === 'running'
    )
  )

export const useBackgroundTaskActions = () =>
  useBackgroundTaskStore((state) => ({
    addTask: state.addTask,
    updateTask: state.updateTask,
    removeTask: state.removeTask,
    clearCompletedTasks: state.clearCompletedTasks,
    getTask: state.getTask,
    getActiveTasksCount: state.getActiveTasksCount,
    getRunningTasks: state.getRunningTasks,
    getPendingTasks: state.getPendingTasks,
  }))
