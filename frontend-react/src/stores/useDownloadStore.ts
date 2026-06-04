import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import { useShallow } from 'zustand/shallow'

export interface DownloadTask {
  id: string
  fileName: string
  serverId?: string
  status: 'downloading' | 'completed' | 'error' | 'cancelled'
  /** 0-100 */
  progress: number
  startTime: number
  endTime?: number
  error?: string
  size?: number
  downloadedSize?: number
  /** bytes per second */
  speed?: number
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
      // AbortController is non-serializable and only meaningful in-process;
      // an in-flight download cannot be resumed across reloads, so mark it cancelled.
      partialize: (state) => ({
        tasks: state.tasks.map(task => ({
          ...task,
          abortController: undefined,
          status: task.status === 'downloading' ? 'cancelled' as const : task.status,
        }))
      }),
    }
  )
)

export const useDownloadTasks = () => useDownloadStore(state => state.tasks)
export const useActiveDownloadTasks = () => useDownloadStore(
  useShallow(state =>
    state.tasks.filter(task => task.status === 'downloading')
  )
)
export const useDownloadActions = () => useDownloadStore(
  useShallow(state => ({
    addTask: state.addTask,
    updateTask: state.updateTask,
    removeTask: state.removeTask,
    cancelTask: state.cancelTask,
    clearCompletedTasks: state.clearCompletedTasks,
    getActiveTasksCount: state.getActiveTasksCount,
    getTask: state.getTask,
  }))
)
