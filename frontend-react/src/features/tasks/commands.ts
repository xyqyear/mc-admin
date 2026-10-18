import { QueryObserver, useMutation, useQueryClient, type QueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { queryKeys, AUTH_EXPIRED_EVENT, getErrorStatus } from '@/shared/http/api'
import type { BackgroundTask, TaskAccepted } from './contracts'
import { useTaskCenterStore } from './panelStore'
import { taskApi } from '@/features/tasks/api'
import { taskQueryKeys } from './queryKeys'
import { retainTaskStream, taskDetailQueryOptions } from './observation'

export async function waitForTaskResult<T>(
  client: QueryClient,
  accepted: TaskAccepted,
  options: { signal?: AbortSignal; onProgress?: (task: BackgroundTask) => void } = {},
): Promise<T> {
  if (options.signal?.aborted) throw new DOMException('已停止观察任务', 'AbortError')
  const controller = new AbortController()
  const abort = () => controller.abort()
  options.signal?.addEventListener('abort', abort, { once: true })
  window.addEventListener(AUTH_EXPIRED_EVENT, abort)
  const warningId = `task-connection-${accepted.task_id}`
  let cleanup: (() => void) | undefined
  const release = retainTaskStream(client)
  void client.invalidateQueries({ queryKey: taskQueryKeys.all })
  void client.invalidateQueries({ queryKey: queryKeys.operations.all })
  try {
    return await new Promise<T>((resolve, reject) => {
      const observer = new QueryObserver(client, { ...taskDetailQueryOptions(client, accepted.task_id, 1000), refetchIntervalInBackground: true })
      const detach = () => reject(new DOMException('已停止观察任务', 'AbortError'))
      controller.signal.addEventListener('abort', detach, { once: true })
      const cacheUnsubscribe = client.getQueryCache().subscribe(event => {
        if (event.type === 'removed' && event.query.queryHash === JSON.stringify(taskQueryKeys.detail(accepted.task_id))) controller.abort()
      })
      const observe = (state: ReturnType<typeof observer.getCurrentResult>) => {
        if (controller.signal.aborted || options.signal?.aborted) { detach(); return }
        if (state.isError) {
          if (getErrorStatus(state.error) === 404) {
            reject(new Error('任务记录已过期或不存在，请刷新相关页面确认操作结果', { cause: state.error }))
          } else toast.warning('暂时无法获取任务状态，正在重新连接', { id: warningId, duration: Infinity })
          return
        }
        const task = state.data
        if (!task) return
        toast.dismiss(warningId)
        try { options.onProgress?.(task) } catch (error) { reject(error); return }
        if (task.status === 'completed') resolve(task.result as T)
        if (task.status === 'failed' || task.status === 'cancelled') reject(Object.assign(new Error(task.error || task.message || '任务未完成'), { code: task.errorCode }))
      }
      const unsubscribe = observer.subscribe(observe)
      observe(observer.getCurrentResult())
      cleanup = () => {
        unsubscribe()
        cacheUnsubscribe()
        controller.signal.removeEventListener('abort', detach)
      }
    })
  } finally {
    cleanup?.()
    release()
    options.signal?.removeEventListener('abort', abort)
    window.removeEventListener(AUTH_EXPIRED_EVENT, abort)
    toast.dismiss(warningId)
    void client.invalidateQueries({ queryKey: taskQueryKeys.all })
    void client.invalidateQueries({ queryKey: queryKeys.operations.all })
  }
}
export const useCancelTask = () => {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: taskApi.cancelTask,
    onSettled: () => { void queryClient.invalidateQueries({ queryKey: queryKeys.operations.all }) },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: taskQueryKeys.all })
    },
  })
}

export const useDeleteTask = () => {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: taskApi.deleteTask,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: taskQueryKeys.all })
    },
  })
}

export const useClearCompletedTasks = () => {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: taskApi.clearCompletedTasks,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: taskQueryKeys.all })
    },
  })
}


export function openTaskCenter() {
  useTaskCenterStore.getState().setActiveTab('background')
  useTaskCenterStore.getState().setOpen(true)
}
