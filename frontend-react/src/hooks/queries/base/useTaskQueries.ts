import { useQuery, useQueryClient } from '@tanstack/react-query'
import { taskApi } from '@/hooks/api/taskApi'
import type { BackgroundTask } from '@/stores/useBackgroundTaskStore'

export const taskQueryKeys = {
  all: ['tasks'] as const,
  active: () => [...taskQueryKeys.all, 'active'] as const,
  detail: (taskId: string) => [...taskQueryKeys.all, taskId] as const,
}

export const useTaskQueries = () => {
  const queryClient = useQueryClient()

  const useTasks = (params?: {
    status?: BackgroundTask['status']
    server_id?: string
    limit?: number
    offset?: number
  }) => {
    return useQuery({
      queryKey: [...taskQueryKeys.all, params],
      queryFn: () => taskApi.getTasks(params),
      staleTime: 1000,
      refetchOnMount: 'always',
      // Tight 1s polling while any task is active, otherwise back off to 10s
      // to avoid burning requests on an idle task center.
      refetchInterval: () => {
        const activeTasksData = queryClient.getQueryData<BackgroundTask[]>(
          taskQueryKeys.active()
        )
        const hasActiveFromCache = activeTasksData && activeTasksData.length > 0
        return hasActiveFromCache ? 1000 : 10000
      },
    })
  }

  const useActiveTasks = () => {
    return useQuery({
      queryKey: taskQueryKeys.active(),
      queryFn: taskApi.getActiveTasks,
      // Same back-off rationale as useTasks above.
      refetchInterval: (query) => {
        const hasActive = query.state.data && query.state.data.length > 0
        return hasActive ? 1000 : 10000
      },
      staleTime: 1000,
      refetchOnMount: 'always',
    })
  }

  const useTask = (taskId: string) => {
    return useQuery({
      queryKey: taskQueryKeys.detail(taskId),
      queryFn: () => taskApi.getTask(taskId),
      enabled: !!taskId,
      // Stop polling once the task reaches a terminal state.
      refetchInterval: (query) => {
        const task = query.state.data
        if (!task) return 2000
        if (task.status === 'running' || task.status === 'pending') {
          return 2000
        }
        return false
      },
      staleTime: 1000,
    })
  }

  return {
    useTasks,
    useActiveTasks,
    useTask,
  }
}
