import { useMutation, useQueryClient } from '@tanstack/react-query'
import { taskApi } from '@/hooks/api/taskApi'
import { taskQueryKeys } from '@/hooks/queries/base/useTaskQueries'

export const useTaskMutations = () => {
  const queryClient = useQueryClient()

  const useCancelTask = () => {
    return useMutation({
      mutationFn: taskApi.cancelTask,
      onSuccess: () => {
        queryClient.invalidateQueries({ queryKey: taskQueryKeys.all })
      },
    })
  }

  const useDeleteTask = () => {
    return useMutation({
      mutationFn: taskApi.deleteTask,
      onSuccess: () => {
        queryClient.invalidateQueries({ queryKey: taskQueryKeys.all })
      },
    })
  }

  const useClearCompletedTasks = () => {
    return useMutation({
      mutationFn: taskApi.clearCompletedTasks,
      onSuccess: () => {
        queryClient.invalidateQueries({ queryKey: taskQueryKeys.all })
      },
    })
  }

  return {
    useCancelTask,
    useDeleteTask,
    useClearCompletedTasks,
  }
}
