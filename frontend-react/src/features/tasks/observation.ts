import { queryOptions, type QueryClient } from '@tanstack/react-query'
import { AUTH_EXPIRED_EVENT } from '@/shared/http/api'
import { readEventStream } from '@/shared/http/eventStream'
import type { OperationChanges } from '@/shared/operations/contracts'
import { taskApi, transformTask } from './api'
import type { BackgroundTask, BackgroundTaskStatus, TaskEvent, TaskEventResponse } from './contracts'
import { taskQueryKeys } from './queryKeys'

export interface TaskFeedState {
  connected: boolean
  error?: string
  tasks?: TaskEvent[]
  activeRestorations?: unknown[]
  pruneStates?: unknown[]
  operationCursor?: string
}

export interface TaskEventSubscriber {
  getOperationCursor?: () => string | undefined
  onOperations?: (changes: OperationChanges, signal: AbortSignal) => void | Promise<void>
}

export interface TaskListParams {
  status?: BackgroundTaskStatus
  server_id?: string
  limit?: number
  offset?: number
}

const transports = new WeakMap<QueryClient, TaskTransport>()
const terminalStatuses = new Set(['completed', 'failed', 'cancelled'])
const isRecord = (value: unknown): value is Record<string, unknown> => !!value && typeof value === 'object' && !Array.isArray(value)

export const taskResultReady = (task?: BackgroundTask) => taskIsTerminal(task) && task?.resultReady === true
export const taskIsTerminal = (task?: BackgroundTask) => !!task && terminalStatuses.has(task.status)
export const taskFeedState = (client: QueryClient) => client.getQueryData<TaskFeedState>(taskQueryKeys.events())

export function parseTaskEvent(value: unknown): TaskEvent {
  if (!isRecord(value) || typeof value.task_id !== 'string' || !value.task_id
    || typeof value.task_type !== 'string' || typeof value.name !== 'string'
    || typeof value.status !== 'string' || !['pending', 'running', 'completed', 'failed', 'cancelled'].includes(value.status)
    || !(value.progress === null || (typeof value.progress === 'number' && Number.isFinite(value.progress)))
    || !(value.progress_details === null || isRecord(value.progress_details))
    || typeof value.message !== 'string' || !(value.server_id === null || typeof value.server_id === 'string')
    || typeof value.created_at !== 'string' || !Number.isFinite(Date.parse(value.created_at))
    || typeof value.cancellable !== 'boolean' || typeof value.result_included !== 'boolean'
    || !(value.result === null || isRecord(value.result))
    || (value.result_included && !terminalStatuses.has(value.status))
    || (!value.result_included && value.result !== null)) throw new Error('任务事件格式无效')
  const event = value as unknown as TaskEventResponse
  return { ...transformTask(event), resultIncluded: event.result_included, resultReady: event.result_included }
}

function pruneTasks(states?: unknown[]) {
  const tasks: TaskEvent[] = []
  for (const state of states ?? []) {
    if (!isRecord(state)) throw new Error('清理任务状态格式无效')
    for (const task of [state.preview_task, state.apply_task]) if (task !== null && task !== undefined) tasks.push(parseTaskEvent(task))
  }
  return tasks
}

function observedEvent(client: QueryClient, taskId: string) {
  const feed = taskFeedState(client)
  return feed?.tasks?.find(task => task.taskId === taskId)
    ?? pruneTasks(feed?.pruneStates).find(task => task.taskId === taskId)
}

export function streamedTaskList(client: QueryClient, params: TaskListParams = {}) {
  const feed = taskFeedState(client)
  if (!feed?.tasks) return undefined
  const tasks = feed.tasks.filter(task => (!params.status || task.status === params.status)
    && (!params.server_id || task.serverId === params.server_id))
  const offset = params.offset ?? 0
  return { tasks: tasks.slice(offset, params.limit === undefined ? undefined : offset + params.limit), total: tasks.length }
}

export function taskDetailQueryOptions(client: QueryClient, taskId: string) {
  return queryOptions({
    queryKey: taskQueryKeys.detail(taskId),
    queryFn: async ({ signal }) => {
      const retained = client.getQueryData<BackgroundTask>(taskQueryKeys.detail(taskId))
      if (taskResultReady(retained)) return retained!
      const summary = observedEvent(client, taskId)
      if (summary && (!taskIsTerminal(summary) || summary.resultIncluded)) return { ...retained, ...summary }
      const task = await taskApi.getTask(taskId, signal)
      signal.throwIfAborted()
      const current = client.getQueryData<BackgroundTask>(taskQueryKeys.detail(taskId))
      if (taskResultReady(current)) return current!
      if (taskResultReady(task)) return task
      const latest = observedEvent(client, taskId)
      if (latest && (!taskIsTerminal(latest) || latest.resultIncluded)) return { ...task, ...latest }
      if (latest && taskIsTerminal(latest) && !taskIsTerminal(task)) return latest
      return task
    },
    enabled: !!taskId,
    staleTime: Infinity,
    retry: false,
    refetchInterval: false,
    refetchOnMount: query => taskResultReady(query.state.data) ? false : 'always',
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
  })
}

class TaskTransport {
  consumers = 0
  private started = false
  private stopped = false
  private reconnectRequested = false
  private controller?: AbortController
  private retryTimer?: ReturnType<typeof setTimeout>
  private idleTimer?: ReturnType<typeof setTimeout>
  private retryDelay = 1000
  private detailReads = new Set<string>()
  private listQueries = new Map<string, readonly unknown[]>()
  private subscribers = new Set<{ options: TaskEventSubscriber; controller: AbortController }>()
  private unsubscribe: () => void

  constructor(private client: QueryClient) {
    if (!taskFeedState(client)) client.setQueryData<TaskFeedState>(taskQueryKeys.events(), { connected: false })
    for (const query of client.getQueryCache().findAll({ queryKey: taskQueryKeys.all })) this.trackList(query.queryHash, query.queryKey)
    this.unsubscribe = client.getQueryCache().subscribe(event => {
      if (event.type === 'added') this.trackList(event.query.queryHash, event.query.queryKey)
      if (event.type === 'removed') this.listQueries.delete(event.query.queryHash)
      if (event.type === 'removed' && event.query.queryHash === JSON.stringify(taskQueryKeys.events())) this.stop(false)
      if (event.type === 'observerAdded' && this.isDetail(event.query.queryKey)) {
        const task = observedEvent(client, event.query.queryKey[1] as string)
        if (task) this.updateDetail(task)
      }
    })
    window.addEventListener(AUTH_EXPIRED_EVENT, this.onAuthExpired)
  }

  private trackList(hash: string, key: readonly unknown[]) {
    if (key.length === 2 && key[0] === 'tasks' && (key[1] === 'active' || typeof key[1] !== 'string')) this.listQueries.set(hash, key)
  }

  reconnect() {
    if (this.stopped) return
    this.reconnectRequested = true
    this.retryDelay = 1000
    clearTimeout(this.retryTimer)
    if (this.controller) this.controller.abort()
    else void this.connect()
  }

  private onAuthExpired = () => this.stop(false)
  private isDetail = (key: readonly unknown[]) => key.length === 2 && key[0] === 'tasks'
    && typeof key[1] === 'string' && key[1] !== 'active' && key[1] !== 'events'
  private observed = (taskId: string) => !!this.client.getQueryCache().find({ queryKey: taskQueryKeys.detail(taskId), exact: true })?.getObserversCount()

  start() {
    if (this.started) return
    this.started = true
    void this.connect()
  }

  subscribe(options: TaskEventSubscriber) {
    const subscriber = { options, controller: new AbortController() }
    this.subscribers.add(subscriber)
    if (options.onOperations) {
      const cursor = options.getOperationCursor?.()
      this.client.setQueryData<TaskFeedState>(taskQueryKeys.events(), current => ({ ...current, connected: current?.connected ?? false, operationCursor: cursor }))
      if (this.started) {
        this.reconnectRequested = true
        this.controller?.abort()
        if (!this.controller) { clearTimeout(this.retryTimer); void this.connect() }
      }
    }
    return () => { subscriber.controller.abort(); this.subscribers.delete(subscriber) }
  }

  stop(updateCache = true) {
    if (this.stopped) return
    this.stopped = true
    clearTimeout(this.retryTimer)
    clearTimeout(this.idleTimer)
    this.controller?.abort()
    for (const subscriber of this.subscribers) subscriber.controller.abort()
    this.subscribers.clear()
    this.unsubscribe()
    window.removeEventListener(AUTH_EXPIRED_EVENT, this.onAuthExpired)
    if (transports.get(this.client) === this) transports.delete(this.client)
    if (!updateCache) void this.client.cancelQueries({ queryKey: taskQueryKeys.all })
    if (updateCache) this.client.setQueryData<TaskFeedState>(taskQueryKeys.events(), current => current ? { ...current, connected: false } : undefined)
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
    this.reconnectRequested = false
    this.activity()
    const cursor = taskFeedState(this.client)?.operationCursor
    const params = cursor === undefined ? '' : `?${new URLSearchParams({ operation_cursor: cursor })}`
    await readEventStream<unknown>({
      url: '/tasks/events' + params, method: 'GET', signal: controller.signal,
      strictJSON: true,
      onActivity: this.activity,
      onResponse: response => {
        if (response.status === 401) { this.stop(false); window.dispatchEvent(new Event(AUTH_EXPIRED_EVENT)) }
        if (response.ok && !response.headers.get('content-type')?.includes('text/event-stream')) throw new Error('任务事件流格式无效')
      },
      onEvent: async event => {
        if (this.stopped || controller.signal.aborted) return
        try {
          await this.receive(event, controller.signal)
          controller.signal.throwIfAborted()
        } catch (error) {
          controller.abort()
          throw error
        }
      },
      onError: () => controller.abort(),
    })
    clearTimeout(this.idleTimer)
    if (this.controller === controller) this.controller = undefined
    if (this.stopped) return
    this.client.setQueryData<TaskFeedState>(taskQueryKeys.events(), current => ({ ...current, connected: false, error: '任务连接已中断，显示的是上次收到的状态' }))
    const delay = this.reconnectRequested ? 0 : this.retryDelay
    this.retryTimer = setTimeout(() => { void this.connect() }, delay)
    this.retryDelay = Math.min(this.retryDelay * 2, 30000)
  }

  private async receive(value: unknown, signal: AbortSignal) {
    if (!isRecord(value)) throw new Error('任务事件格式无效')
    const previous = taskFeedState(this.client)
    if (value.type === 'operation_changes') {
      if (!isRecord(value.changes) || !Array.isArray(value.changes.items)
        || typeof value.changes.next_cursor !== 'string' || typeof value.changes.reset_required !== 'boolean'
        || typeof value.changes.active_count !== 'number' || !Number.isInteger(value.changes.active_count) || value.changes.active_count < 0
        || typeof value.changes.has_more !== 'boolean'
        || !value.changes.items.every(operation => isRecord(operation)
          && typeof operation.operation_id === 'string' && typeof operation.kind === 'string' && typeof operation.state === 'string'
          && typeof operation.data_changed === 'boolean' && typeof operation.updated_at === 'string'
          && (operation.ended_at === null || typeof operation.ended_at === 'string')
          && typeof operation.sequence === 'number' && Number.isInteger(operation.sequence) && operation.sequence >= 0
          && Array.isArray(operation.resources) && operation.resources.every(resource => isRecord(resource)
            && typeof resource.kind === 'string' && typeof resource.path === 'string'
            && (resource.server_id === null || typeof resource.server_id === 'string')
            && (resource.generation === null || (typeof resource.generation === 'number' && Number.isFinite(resource.generation)))))) throw new Error('操作事件格式无效')
      const changes = value.changes as unknown as OperationChanges
      const subscribers = [...this.subscribers].filter(subscriber => subscriber.options.onOperations)
      if (!subscribers.length) return
      for (const subscriber of subscribers) {
        const operationSignal = AbortSignal.any([signal, subscriber.controller.signal])
        operationSignal.throwIfAborted()
        await subscriber.options.onOperations!(changes, operationSignal)
        operationSignal.throwIfAborted()
      }
      signal.throwIfAborted()
      this.client.setQueryData<TaskFeedState>(taskQueryKeys.events(), current => ({ ...current, connected: current?.connected ?? false, operationCursor: changes.next_cursor }))
      return
    }
    let tasks = previous?.tasks ?? []
    let changed: TaskEvent[] = []
    let activeRestorations = previous?.activeRestorations
    let pruneStates = previous?.pruneStates
    if (value.type === 'snapshot' && Array.isArray(value.tasks) && Array.isArray(value.active_restorations) && Array.isArray(value.prune_states)) {
      tasks = value.tasks.map(parseTaskEvent)
      changed = tasks
      activeRestorations = value.active_restorations
      pruneStates = value.prune_states
      this.retryDelay = 1000
    } else if (value.type === 'upsert' && previous?.connected) {
      const task = parseTaskEvent(value.task)
      tasks = [...tasks.filter(row => row.taskId !== task.taskId), task]
      changed = [task]
    } else if (value.type === 'remove' && previous?.connected && typeof value.task_id === 'string') {
      tasks = tasks.filter(row => row.taskId !== value.task_id)
    } else if (value.type === 'restoration_index' && previous?.connected && Array.isArray(value.active_restorations)) {
      activeRestorations = value.active_restorations
    } else if (value.type === 'prune_state' && previous?.connected && Array.isArray(value.prune_states)) {
      pruneStates = value.prune_states
    } else throw new Error('任务事件格式无效')
    const retainedTasks = value.type === 'snapshot' || value.type === 'prune_state' ? pruneTasks(pruneStates) : []
    this.client.setQueryData<TaskFeedState>(taskQueryKeys.events(), { ...previous, connected: true, error: undefined, tasks, activeRestorations, pruneStates })
    for (const key of changed.length || value.type === 'snapshot' || value.type === 'remove' ? this.listQueries.values() : []) {
      if (key[1] === 'active') this.client.setQueryData(key, tasks.filter(task => !taskIsTerminal(task)))
      else if (typeof key[1] !== 'string') this.client.setQueryData(key, streamedTaskList(this.client, key[1] as TaskListParams | undefined))
    }
    for (const task of [...changed, ...retainedTasks]) this.updateDetail(task)
  }

  private updateDetail(task: TaskEvent) {
    const key = taskQueryKeys.detail(task.taskId)
    const query = this.client.getQueryCache().find({ queryKey: key, exact: true })
    if (!query) return
    const previous = query.state.data as BackgroundTask | undefined
    if (taskResultReady(previous)) return
    if (!taskIsTerminal(task) || task.resultIncluded) {
      this.client.setQueryData<BackgroundTask>(key, task)
      return
    }
    this.client.setQueryData<BackgroundTask>(key, task)
    if (this.observed(task.taskId)) this.refreshDetail(task.taskId)
  }

  private refreshDetail(taskId: string) {
    if (this.detailReads.has(taskId)) return
    this.detailReads.add(taskId)
    const joined = this.client.getQueryState(taskQueryKeys.detail(taskId))?.fetchStatus === 'fetching'
    void (async () => {
      try {
        await this.client.fetchQuery({ ...taskDetailQueryOptions(this.client, taskId), staleTime: 0 })
        if (joined && !this.stopped && this.observed(taskId) && !taskResultReady(this.client.getQueryData<BackgroundTask>(taskQueryKeys.detail(taskId)))) {
          await this.client.fetchQuery({ ...taskDetailQueryOptions(this.client, taskId), staleTime: 0 })
        }
      } catch { /* Only a later observation or explicit retry reads an excluded result again. */ }
    })().finally(() => this.detailReads.delete(taskId))
  }
}

function transportFor(client: QueryClient) {
  let transport = transports.get(client)
  if (!transport) { transport = new TaskTransport(client); transports.set(client, transport) }
  return transport
}

function retain(transport: TaskTransport) {
  transport.consumers++
  transport.start()
  let released = false
  return () => { if (!released) { released = true; if (--transport.consumers === 0) transport.stop() } }
}

export function retainTaskStream(client: QueryClient) {
  return retain(transportFor(client))
}

export function subscribeTaskEvents(client: QueryClient, subscriber: TaskEventSubscriber) {
  const transport = transportFor(client)
  const unsubscribe = transport.subscribe(subscriber)
  const release = retain(transport)
  return () => { unsubscribe(); release() }
}

export function retryTaskObservation(client: QueryClient) {
  transportFor(client).reconnect()
}
