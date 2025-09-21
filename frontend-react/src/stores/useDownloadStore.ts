import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export interface DownloadTask {
  id: string
  fileName: string
  serverId?: string
  status: 'downloading' | 'completed' | 'error' | 'cancelled'
  progress: number // 0-100
  startTime: number
  endTime?: number
  error?: string
  size?: number
  downloadedSize?: number
  speed?: number // bytes per second
  abortController?: AbortController
}

interface DownloadState {
  tasks: DownloadTask[]
  addTask: (task: Omit<DownloadTask, 'id' | 'startTime'>) => string
  updateTask: (id: string, updates: Partial<DownloadTask>) => void
  removeTask: (id: string) => void
  cancelTask: (id: string) => void
  clearCompletedTasks: () => void
  getActiveTasksCount: () => number
  getTask: (id: string) => DownloadTask | undefined
}

export const useDownloadStore = create<DownloadState>()(
  persist(
    (set, get) => ({
      tasks: [],

      addTask: (taskData) => {
        const id = `download_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`
        const newTask: DownloadTask = {
          ...taskData,
          id,
          startTime: Date.now(),
          status: 'downloading',
          progress: 0,
        }

        set((state) => ({
          tasks: [...state.tasks, newTask]
        }))

        return id
      },

      updateTask: (id, updates) => {
        set((state) => ({
          tasks: state.tasks.map(task =>
            task.id === id ? { ...task, ...updates } : task
          )
        }))
      },

      removeTask: (id) => {
        set((state) => ({
          tasks: state.tasks.filter(task => task.id !== id)
        }))
      },

      cancelTask: (id) => {
        const task = get().getTask(id)
        if (task?.abortController) {
          task.abortController.abort()
        }

        set((state) => ({
          tasks: state.tasks.map(task =>
            task.id === id
              ? { ...task, status: 'cancelled' as const, endTime: Date.now() }
              : task
          )
        }))
      },

      clearCompletedTasks: () => {
        set((state) => ({
          tasks: state.tasks.filter(task =>
            task.status === 'downloading'
          )
        }))
      },

      getActiveTasksCount: () => {
        return get().tasks.filter(task => task.status === 'downloading').length
      },

      getTask: (id) => {
        return get().tasks.find(task => task.id === id)
      },
    }),
    {
      name: 'download-store',
      // 只持久化任务基本信息，不持久化 AbortController
      partialize: (state) => ({
        tasks: state.tasks.map(task => ({
          ...task,
          abortController: undefined, // 不持久化AbortController
          status: task.status === 'downloading' ? 'cancelled' as const : task.status, // 重启时取消进行中的任务
        }))
      }),
    }
  )
)

// 导出选择器钩子以优化性能
export const useDownloadTasks = () => useDownloadStore(state => state.tasks)
export const useActiveDownloadTasks = () => useDownloadStore(state =>
  state.tasks.filter(task => task.status === 'downloading')
)
export const useDownloadActions = () => useDownloadStore(state => ({
  addTask: state.addTask,
  updateTask: state.updateTask,
  removeTask: state.removeTask,
  cancelTask: state.cancelTask,
  clearCompletedTasks: state.clearCompletedTasks,
  getActiveTasksCount: state.getActiveTasksCount,
  getTask: state.getTask,
}))