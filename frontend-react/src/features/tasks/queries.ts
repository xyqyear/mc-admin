import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect } from 'react'
import { taskApi } from '@/features/tasks/api'
import type { BackgroundTask } from './contracts'
import { taskQueryKeys } from './queryKeys'
import { retainTaskStream, streamedTaskList, taskDetailQueryOptions, taskFeedState, type TaskFeedState, type TaskListParams } from './observation'

export { taskQueryKeys } from './queryKeys'

function useTaskStream(enabled = true) {
  const client = useQueryClient()
  useQuery<TaskFeedState>({
    queryKey: taskQueryKeys.events(),
    queryFn: () => ({ connected: false }),
    enabled: false,
    initialData: { connected: false },
    gcTime: Infinity,
  })
  useEffect(() => enabled ? retainTaskStream(client) : undefined, [client, enabled])
  return client
}

export const useTasks = (params?: TaskListParams) => {
  const queryClient = useTaskStream()
  return useQuery({
    queryKey: taskQueryKeys.list(params),
    queryFn: async ({ signal }) => {
      const data = await taskApi.getTasks(params, signal)
      signal.throwIfAborted()
      return streamedTaskList(queryClient, params) ?? data
    },
    staleTime: 1000,
    refetchOnMount: 'always',
    refetchInterval: () => {
      if (taskFeedState(queryClient)?.connected) return false
      const activeTasksData = queryClient.getQueryData<BackgroundTask[]>(
        taskQueryKeys.active()
      )
      const hasActiveFromCache = activeTasksData && activeTasksData.length > 0
      return hasActiveFromCache ? 1000 : 10000
    },
  })
}

export const useActiveTasks = () => {
  const client = useTaskStream()
  return useQuery({
    queryKey: taskQueryKeys.active(),
    queryFn: async ({ signal }) => {
      const tasks = await taskApi.getActiveTasks(signal)
      signal.throwIfAborted()
      const feed = taskFeedState(client)
      return feed?.connected && feed.tasks ? feed.tasks.filter(task => task.status === 'pending' || task.status === 'running') : tasks
    },
    refetchInterval: (query) => {
      if (taskFeedState(client)?.connected) return false
      const hasActive = query.state.data && query.state.data.length > 0
      return hasActive ? 1000 : 10000
    },
    staleTime: 1000,
    refetchOnMount: 'always',
  })
}

export const useTask = (taskId: string) => {
  const client = useTaskStream(!!taskId)
  return useQuery(taskDetailQueryOptions(client, taskId))
}
