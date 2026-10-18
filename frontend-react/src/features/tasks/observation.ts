import { queryOptions, type QueryClient } from '@tanstack/react-query'
import { AUTH_EXPIRED_EVENT, getErrorStatus } from '@/shared/http/api'
import { readEventStream } from '@/shared/http/eventStream'
import { taskApi, transformTask } from './api'
import type { BackgroundTask, BackgroundTaskResponse, BackgroundTaskStatus } from './contracts'
import { taskQueryKeys } from './queryKeys'

export interface TaskFeedState {
  connected: boolean
  tasks?: BackgroundTask[]
}

export interface TaskListParams {
  status?: BackgroundTaskStatus
  server_id?: string
  limit?: number
  offset?: number
}

const transports = new WeakMap<QueryClient, TaskTransport>()
const terminalStatuses = new Set(['completed', 'failed', 'cancelled'])
const progressResultTypes = new Set(['map_initialize', 'self_check'])

export const taskIsTerminal = (task?: BackgroundTask) => !!task && terminalStatuses.has(task.status)
export const taskFeedState = (client: QueryClient) => client.getQueryData<TaskFeedState>(taskQueryKeys.events())

export function streamedTaskList(client: QueryClient, params: TaskListParams = {}) {
  const feed = taskFeedState(client)
  if (!feed?.connected || !feed.tasks) return undefined
  const tasks = feed.tasks.filter(task => (!params.status || task.status === params.status)
    && (!params.server_id || task.serverId === params.server_id))
  const offset = params.offset ?? 0
  return { tasks: tasks.slice(offset, params.limit === undefined ? undefined : offset + params.limit), total: tasks.length }
}

export function taskDetailQueryOptions(client: QueryClient, taskId: string, interval = 2000) {
  return queryOptions({
    queryKey: taskQueryKeys.detail(taskId),
    queryFn: async ({ signal }) => {
      const task = await taskApi.getTask(taskId, signal)
      signal.throwIfAborted()
      const retained = client.getQueryData<BackgroundTask>(taskQueryKeys.detail(taskId))
      if (taskIsTerminal(retained)) return retained!
      if (taskIsTerminal(task)) return task
      const feed = taskFeedState(client)
      const summary = feed?.connected ? feed.tasks?.find(row => row.taskId === taskId) : undefined
      return summary && !taskIsTerminal(summary) ? { ...task, ...summary, result: task.result } : task
    },
    enabled: !!taskId,
    staleTime: 1000,
    retry: false,
    refetchInterval: query => {
      if (taskIsTerminal(query.state.data) || getErrorStatus(query.state.error) === 404) return false
      const feed = taskFeedState(client)
      const summary = feed?.tasks?.find(task => task.taskId === taskId)
      return !feed?.connected || !summary || taskIsTerminal(summary) || query.state.status === 'error' ? interval : false
    },
  })
}

function isTaskSummary(value: unknown): value is BackgroundTaskResponse {
  if (!value || typeof value !== 'object') return false
  const task = value as Record<string, unknown>
  return typeof task.task_id === 'string' && !!task.task_id && typeof task.task_type === 'string'
    && typeof task.name === 'string' && typeof task.status === 'string'
    && ['pending', 'running', 'completed', 'failed', 'cancelled'].includes(task.status)
    && (task.progress === null || (typeof task.progress === 'number' && Number.isFinite(task.progress)))
    && typeof task.message === 'string' && (task.server_id === null || typeof task.server_id === 'string')
    && typeof task.created_at === 'string' && Number.isFinite(Date.parse(task.created_at))
    && typeof task.cancellable === 'boolean'
}

function summaryTask(value: BackgroundTaskResponse): BackgroundTask {
  return { ...transformTask(value), result: undefined }
}

class TaskTransport {
  consumers = 0
  private stopped = false
  private controller?: AbortController
  private retryTimer?: ReturnType<typeof setTimeout>
  private idleTimer?: ReturnType<typeof setTimeout>
  private retryDelay = 1000
  private detailReads = new Map<string, { dirty: boolean }>()
  private unsubscribe: () => void

  constructor(private client: QueryClient) {
    if (!taskFeedState(client)) client.setQueryData<TaskFeedState>(taskQueryKeys.events(), { connected: false })
    this.unsubscribe = client.getQueryCache().subscribe(event => {
      if (event.type === 'removed' && event.query.queryHash === JSON.stringify(taskQueryKeys.events())) this.stop(false)
      if (event.type === 'observerAdded' && this.isDetail(event.query.queryKey)) {
        const summary = taskFeedState(client)?.tasks?.find(task => task.taskId === event.query.queryKey[1])
        if (summary && taskFeedState(client)?.connected) this.updateDetail(summary)
      }
    })
    window.addEventListener(AUTH_EXPIRED_EVENT, this.onAuthExpired)
  }

  private onAuthExpired = () => this.stop(false)
  private isDetail = (key: readonly unknown[]) => key.length === 2 && key[0] === 'tasks'
    && typeof key[1] === 'string' && key[1] !== 'active' && key[1] !== 'events'
  private observed = (taskId: string) => !!this.client.getQueryCache().find({ queryKey: taskQueryKeys.detail(taskId), exact: true })?.getObserversCount()

  start() { void this.connect() }

  stop(updateCache = true) {
    if (this.stopped) return
    this.stopped = true
    clearTimeout(this.retryTimer)
    clearTimeout(this.idleTimer)
    this.controller?.abort()
    this.unsubscribe()
    window.removeEventListener(AUTH_EXPIRED_EVENT, this.onAuthExpired)
    if (transports.get(this.client) === this) transports.delete(this.client)
    if (!updateCache) void this.client.cancelQueries({ queryKey: taskQueryKeys.all })
    if (updateCache) {
      this.client.setQueryData<TaskFeedState>(taskQueryKeys.events(), current => current ? { ...current, connected: false } : undefined)
    }
  }

  private activity = () => {
    if (this.stopped) return
    clearTimeout(this.idleTimer)
    this.idleTimer = setTimeout(() => this.controller?.abort(), 45000)
  }

  private async connect() {
    if (this.stopped) return
    const controller = new AbortController()
    this.controller = controller
    this.activity()
    await readEventStream<unknown>({
      url: '/tasks/events', method: 'GET', signal: controller.signal,
      strictJSON: true,
      onActivity: this.activity,
      onResponse: response => {
        if (response.status === 401) {
          this.stop(false)
          window.dispatchEvent(new Event(AUTH_EXPIRED_EVENT))
        }
        if (response.ok && !response.headers.get('content-type')?.includes('text/event-stream')) throw new Error('任务事件流格式无效')
      },
      onEvent: event => { if (!this.stopped && !controller.signal.aborted) this.receive(event) },
      onError: () => controller.abort(),
    })
    clearTimeout(this.idleTimer)
    if (this.stopped) return
    const wasConnected = taskFeedState(this.client)?.connected
    this.client.setQueryData<TaskFeedState>(taskQueryKeys.events(), current => ({ ...current, connected: false }))
    if (wasConnected) void this.client.invalidateQueries({ queryKey: taskQueryKeys.all, predicate: query => query.queryKey[1] !== 'events' && getErrorStatus(query.state.error) !== 404 }, { cancelRefetch: false })
    this.retryTimer = setTimeout(() => { void this.connect() }, this.retryDelay)
    this.retryDelay = Math.min(this.retryDelay * 2, 30000)
  }

  private receive(value: unknown) {
    if (!value || typeof value !== 'object') throw new Error('任务事件格式无效')
    const event = value as Record<string, unknown>
    const previous = taskFeedState(this.client)
    let tasks: BackgroundTask[]
    let changed: BackgroundTask[]
    if (event.type === 'snapshot' && Array.isArray(event.tasks) && event.tasks.every(isTaskSummary)) {
      tasks = event.tasks.map(summaryTask)
      changed = tasks
      this.retryDelay = 1000
    } else if (event.type === 'upsert' && previous?.connected && isTaskSummary(event.task)) {
      const task = summaryTask(event.task)
      tasks = [...(previous.tasks ?? []).filter(row => row.taskId !== task.taskId), task]
      changed = [task]
    } else if (event.type === 'remove' && previous?.connected && typeof event.task_id === 'string') {
      tasks = (previous.tasks ?? []).filter(row => row.taskId !== event.task_id)
      changed = []
    } else throw new Error('任务事件格式无效')
    this.client.setQueryData<TaskFeedState>(taskQueryKeys.events(), { connected: true, tasks })
    for (const query of this.client.getQueryCache().findAll({ queryKey: taskQueryKeys.all })) {
      const key = query.queryKey
      if (key.length !== 2) continue
      if (key[1] === 'active') this.client.setQueryData(key, tasks.filter(task => !taskIsTerminal(task)))
      else if (typeof key[1] !== 'string') this.client.setQueryData(key, streamedTaskList(this.client, key[1] as TaskListParams | undefined))
    }
    for (const task of changed) if (this.observed(task.taskId)) this.updateDetail(task)
  }

  private updateDetail(summary: BackgroundTask) {
    const key = taskQueryKeys.detail(summary.taskId)
    const previous = this.client.getQueryData<BackgroundTask>(key)
    if (taskIsTerminal(previous)) return
    if (!taskIsTerminal(summary)) {
      this.client.setQueryData<BackgroundTask>(key, { ...previous, ...summary, result: previous?.result })
    }
    if (taskIsTerminal(summary) || progressResultTypes.has(summary.taskType)) this.refreshDetail(summary.taskId)
  }

  private refreshDetail(taskId: string) {
    const pending = this.detailReads.get(taskId)
    if (pending) { pending.dirty = true; return }
    const read = { dirty: false }
    this.detailReads.set(taskId, read)
    const joined = this.client.getQueryState(taskQueryKeys.detail(taskId))?.fetchStatus === 'fetching'
    void (async () => {
      let repeat = joined
      for (;;) {
        read.dirty = false
        try { await this.client.fetchQuery({ ...taskDetailQueryOptions(this.client, taskId), staleTime: 0 }) } catch { /* HTTP recovery retains the observer's guard. */ }
        if (this.stopped || !this.observed(taskId) || taskIsTerminal(this.client.getQueryData<BackgroundTask>(taskQueryKeys.detail(taskId)))) break
        const again = repeat || read.dirty
        repeat = false
        if (!again) break
      }
    })().finally(() => this.detailReads.delete(taskId))
  }
}

export function retainTaskStream(client: QueryClient) {
  let transport = transports.get(client)
  if (!transport) {
    transport = new TaskTransport(client)
    transports.set(client, transport)
    transport.start()
  }
  transport.consumers++
  const retained = transport
  let released = false
  return () => {
    if (released) return
    released = true
    if (--retained.consumers === 0) retained.stop()
  }
}
