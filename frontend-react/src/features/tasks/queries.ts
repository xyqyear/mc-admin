import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect } from 'react'
import { taskApi } from '@/features/tasks/api'
import { taskQueryKeys } from './queryKeys'
import { retainTaskStream, streamedTaskList, taskDetailQueryOptions, taskFeedState, taskIsTerminal, taskResultReady, type TaskFeedState, type TaskListParams } from './observation'

export { taskQueryKeys } from './queryKeys'
export { parseTaskEvent, subscribeTaskEvents, retryTaskObservation } from './observation'
export type { TaskFeedState, TaskEventSubscriber } from './observation'

function useTaskStream(enabled = true) {
  const client = useQueryClient()
  const { data } = useQuery<TaskFeedState>({
    queryKey: taskQueryKeys.events(),
    queryFn: () => ({ connected: false }),
    enabled: false,
    initialData: { connected: false },
    gcTime: Infinity,
  })
  useEffect(() => enabled ? retainTaskStream(client) : undefined, [client, enabled])
  return { client, feed: data }
}

export function useTaskFeed(enabled = true): TaskFeedState {
  return useTaskStream(enabled).feed
}

export const useTasks = (params?: TaskListParams) => {
  const { client } = useTaskStream()
  return useQuery({
    queryKey: taskQueryKeys.list(params),
    queryFn: async ({ signal }) => {
      const streamed = streamedTaskList(client, params)
      if (streamed) return streamed
      const data = await taskApi.getTasks(params, signal)
      signal.throwIfAborted()
      return streamedTaskList(client, params) ?? data
    },
    staleTime: Infinity,
    refetchInterval: false,
    refetchOnMount: false,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
  })
}

export const useActiveTasks = () => {
  const { client } = useTaskStream()
  return useQuery({
    queryKey: taskQueryKeys.active(),
    queryFn: async ({ signal }) => {
      const current = taskFeedState(client)?.tasks
      if (current) return current.filter(task => task.status === 'pending' || task.status === 'running')
      const tasks = await taskApi.getActiveTasks(signal)
      signal.throwIfAborted()
      const feed = taskFeedState(client)
      return feed?.tasks ? feed.tasks.filter(task => task.status === 'pending' || task.status === 'running') : tasks
    },
    refetchInterval: false,
    staleTime: Infinity,
    refetchOnMount: false,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
  })
}

export const useTask = (taskId: string) => {
  const { client, feed } = useTaskStream(!!taskId)
  const query = useQuery(taskDetailQueryOptions(client, taskId))
  const reconnecting = !!taskId && feed.tasks !== undefined && !feed.connected && !taskIsTerminal(query.data)
  const resultReady = taskResultReady(query.data)
  const isAwaitingResult = taskIsTerminal(query.data) && !resultReady
  const resultError = isAwaitingResult && query.isError ? query.error : null
  return { ...query, reconnecting, resultReady, resultError, isAwaitingResult, retryResult: query.refetch, isError: query.isError || reconnecting }
}
