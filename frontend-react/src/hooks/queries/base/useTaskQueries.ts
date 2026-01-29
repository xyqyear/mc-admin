import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { taskApi } from '@/hooks/api/taskApi'
import type { BackgroundTask } from '@/stores/useBackgroundTaskStore'

export const taskQueryKeys = {
  all: ['tasks'] as const,
  active: () => [...taskQueryKeys.all, 'active'] as const,
  detail: (taskId: string) => [...taskQueryKeys.all, taskId] as const,
}

export const useTaskQueries = () => {
  const queryClient = useQueryClient()

  // Get all tasks
  const useTasks = (params?: {
    status?: BackgroundTask['status']
    server_id?: string
    limit?: number
    offset?: number
  }) => {
    return useQuery({
      queryKey: [...taskQueryKeys.all, params],
      queryFn: () => taskApi.getTasks(params),
      staleTime: 5000, // 5 seconds
    })
  }

  // Get active tasks with dynamic polling
  const useActiveTasks = () => {
    return useQuery({
      queryKey: taskQueryKeys.active(),
      queryFn: taskApi.getActiveTasks,
      refetchInterval: (query) => {
        // Poll every 2 seconds if there are active tasks, otherwise 30 seconds
        const hasActive = query.state.data && query.state.data.length > 0
        return hasActive ? 2000 : 30000
      },
      staleTime: 1000,
    })
  }

  // Get single task
  const useTask = (taskId: string) => {
    return useQuery({
      queryKey: taskQueryKeys.detail(taskId),
      queryFn: () => taskApi.getTask(taskId),
      enabled: !!taskId,
      refetchInterval: (query) => {
        const task = query.state.data
        if (!task) return false
        // Poll every 2 seconds for running/pending tasks
        if (task.status === 'running' || task.status === 'pending') {
          return 2000
        }
        return false
      },
      staleTime: 1000,
    })
  }

  // Cancel task mutation
  const useCancelTask = () => {
    return useMutation({
      mutationFn: taskApi.cancelTask,
      onSuccess: () => {
        queryClient.invalidateQueries({ queryKey: taskQueryKeys.all })
      },
    })
  }

  // Delete task mutation
  const useDeleteTask = () => {
    return useMutation({
      mutationFn: taskApi.deleteTask,
      onSuccess: () => {
        queryClient.invalidateQueries({ queryKey: taskQueryKeys.all })
      },
    })
  }

  // Clear completed tasks mutation
  const useClearCompletedTasks = () => {
    return useMutation({
      mutationFn: taskApi.clearCompletedTasks,
      onSuccess: () => {
        queryClient.invalidateQueries({ queryKey: taskQueryKeys.all })
      },
    })
  }

  return {
    useTasks,
    useActiveTasks,
    useTask,
    useCancelTask,
    useDeleteTask,
    useClearCompletedTasks,
  }
}
