import { useMutation, useQueryClient, type QueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { queryKeys, AUTH_EXPIRED_EVENT, getErrorStatus } from '@/shared/http/api'
import type { BackgroundTask, TaskAccepted } from './contracts'
import { useTaskCenterStore } from './panelStore'
import { taskApi } from '@/features/tasks/api'
import { taskQueryKeys } from '@/features/tasks/queries'

export async function waitForTaskResult<T>(
  client: QueryClient,
  accepted: TaskAccepted,
  options: { signal?: AbortSignal; onProgress?: (task: BackgroundTask) => void } = {},
): Promise<T> {
  const controller = new AbortController()
  const abort = () => controller.abort()
  options.signal?.addEventListener('abort', abort, { once: true })
  window.addEventListener(AUTH_EXPIRED_EVENT, abort)
  const warningId = `task-connection-${accepted.task_id}`
  void client.invalidateQueries({ queryKey: taskQueryKeys.all })
  void client.invalidateQueries({ queryKey: queryKeys.operations.all })
  try {
    for (;;) {
      if (controller.signal.aborted || options.signal?.aborted) throw new DOMException('已停止观察任务', 'AbortError')
      let task: BackgroundTask | undefined
      try {
        task = await taskApi.getTask(accepted.task_id)
      } catch (error) {
        if (getErrorStatus(error) === 404) throw new Error('任务记录已过期或不存在，请刷新相关页面确认操作结果', { cause: error })
        if (!controller.signal.aborted) toast.warning('暂时无法获取任务状态，正在重新连接', { id: warningId, duration: Infinity })
      }
      if (controller.signal.aborted || options.signal?.aborted) throw new DOMException('已停止观察任务', 'AbortError')
      if (task) {
        toast.dismiss(warningId)
        client.setQueryData(taskQueryKeys.detail(task.taskId), task)
        options.onProgress?.(task)
        if (task.status === 'completed') return task.result as T
        if (task.status === 'failed' || task.status === 'cancelled') {
          throw Object.assign(new Error(task.error || task.message || '任务未完成'), { code: task.errorCode })
        }
      }
      await new Promise<void>(resolve => {
        const finish = () => { clearTimeout(timer); controller.signal.removeEventListener('abort', finish); resolve() }
        const timer = setTimeout(finish, 1000)
        controller.signal.addEventListener('abort', finish, { once: true })
      })
    }
  } finally {
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
