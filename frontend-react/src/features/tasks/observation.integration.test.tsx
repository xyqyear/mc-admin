import { act, renderHook, waitFor } from '@testing-library/react'
import { afterAll, afterEach, beforeAll, beforeEach, expect, it, vi } from 'vitest'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { AUTH_EXPIRED_EVENT } from '@/shared/http/api'
import { createTestClient, deferred } from '@/test/http'
import { TestProviders } from '@/test/TestProviders'
import { createTaskEvents, taskResponse } from '@/test/taskEvents'
import { useCancelTask, waitForTaskResult } from './commands'
import { taskQueryKeys, useActiveTasks, useTask, useTasks, useTaskFeed, subscribeTaskEvents } from './queries'
import type { BackgroundTask } from './contracts'

const server = setupServer()
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterAll(() => server.close())
let client: ReturnType<typeof createTestClient>
beforeEach(() => { client = createTestClient() })
afterEach(() => { client.clear(); server.resetHandlers(); vi.useRealTimers(); vi.restoreAllMocks() })
const wrapper = ({ children }: { children: React.ReactNode }) => <TestProviders client={client}>{children}</TestProviders>

it('shares one live connection across lists, details and waiters without periodic progress reads', async () => {
  const task = taskResponse('backup', { progress: 5 })
  const feed = createTaskEvents([task])
  let detailReads = 0
  let listReads = 0
  server.use(feed.handler,
    http.get('*/api/tasks', () => { listReads++; return HttpResponse.json({ tasks: [task], total: 1 }) }),
    http.get('*/api/tasks/backup', () => { detailReads++; return HttpResponse.json(task) }),
  )
  const view = renderHook(() => ({ list: useTasks(), active: useActiveTasks(), detail: useTask('backup') }), { wrapper })
  const ctrl = new AbortController()
  const progress: Array<number | null> = []
  const waiting = waitForTaskResult<never>(client, { task_id: 'backup' }, { signal: ctrl.signal, onProgress: row => progress.push(row.progress) }).catch((error: Error) => error)
  await waitFor(() => expect(view.result.current.list.data?.tasks[0].progress).toBe(5))
  await waitFor(() => expect(feed.connections).toBe(1))
  act(() => feed.upsert({ ...task, progress: 100, message: '正在完成清理' }))
  await waitFor(() => expect(view.result.current.detail.data?.progress).toBe(100))
  expect(view.result.current.detail.data?.status).toBe('running')
  expect(view.result.current.active.data).toHaveLength(1)
  expect(progress).toContain(100)
  const reads = { detailReads, listReads }
  vi.useFakeTimers()
  await act(async () => { await vi.advanceTimersByTimeAsync(5000) })
  expect({ detailReads, listReads }).toEqual(reads)
  vi.useRealTimers()
  view.unmount()
  expect(feed.activeConnections).toBe(1)
  ctrl.abort()
  expect((await waiting).name).toBe('AbortError')
  await waitFor(() => expect(feed.activeConnections).toBe(0))
})

it('keeps the guard until terminal detail is readable and returns its complete result', async () => {
  const task = taskResponse('backup', { progress: 10 })
  const feed = createTaskEvents([task])
  const finalRead = deferred<void>()
  let completed = false
  let failDetail = true
  let finalReads = 0
  server.use(feed.handler,
    http.get('*/api/tasks/backup', async () => {
      if (!completed) return HttpResponse.json(task)
      finalReads++
      await finalRead.promise
      return failDetail ? new HttpResponse(null, { status: 503 }) : HttpResponse.json({ ...task, status: 'completed', result: { snapshot: { short_id: 'real-result' }, skipped_paths: ['protected'] } })
    }),
  )
  const view = renderHook(() => {
    const task = useTask('backup')
    return task
  }, { wrapper })
  let settled = false
  const waiting = waitForTaskResult<{ snapshot: { short_id: string }; skipped_paths: string[] }>(client, { task_id: 'backup' }).then(result => { settled = true; return result })
  void waiting.catch(() => {})
  await waitFor(() => expect(view.result.current.data?.status).toBe('running'))
  completed = true
  act(() => feed.upsert({ ...task, status: 'completed', progress: 100, result_included: false }))
  await waitFor(() => expect(finalReads).toBe(1))
  expect(view.result.current.data?.status).toBe('completed')
  expect(view.result.current.resultReady).toBe(false)
  expect(view.result.current.isAwaitingResult).toBe(true)
  expect(settled).toBe(false)
  await act(async () => { finalRead.resolve() })
  await waitFor(() => expect(view.result.current.isError).toBe(true))
  expect(settled).toBe(false)
  failDetail = false
  await act(async () => { await view.result.current.retryResult() })
  expect(await waiting).toEqual({ snapshot: { short_id: 'real-result' }, skipped_paths: ['protected'] })
  await waitFor(() => expect(view.result.current.data?.status).toBe('completed'))
})

it('retains guarded state after EOF and recovers only through the next snapshot without HTTP polling', async () => {
  const task = taskResponse('backup', { progress: 10 })
  const feed = createTaskEvents([task])
  let reads = 0
  let writes = 0
  server.use(feed.handler,
    http.get('*/api/tasks', () => { reads++; return HttpResponse.json({ tasks: [task], total: 1 }) }),
    http.post('*/api/*', () => { writes++; return HttpResponse.json({}) }),
  )
  const view = renderHook(() => ({ list: useTasks(), feed: useTaskFeed() }), { wrapper })
  await waitFor(() => expect(view.result.current.feed.connected).toBe(true))
  const initialReads = reads
  feed.replace([{ ...task, progress: 70 }])
  act(() => feed.close())
  await waitFor(() => expect(view.result.current.feed.connected).toBe(false))
  expect(view.result.current.list.data?.tasks[0].progress).toBe(10)
  await waitFor(() => expect(feed.connections).toBe(2), { timeout: 2500 })
  await waitFor(() => expect(view.result.current.list.data?.tasks[0].progress).toBe(70))
  expect(reads).toBe(initialReads)
  expect(writes).toBe(0)
})

it('recovers a lost terminal frame from a new snapshot when malformed JSON is followed by keepalive', async () => {
  const task = taskResponse('backup')
  const feed = createTaskEvents([task])
  let reads = 0
  server.use(feed.handler, http.get('*/api/tasks/backup', () => { reads++; return HttpResponse.json(task) }))
  const progress = vi.fn()
  const waiting = waitForTaskResult(client, { task_id: 'backup' }, { onProgress: progress })
  void waiting.catch(() => {})
  await waitFor(() => expect(feed.activeConnections).toBe(1))
  await waitFor(() => expect(progress).toHaveBeenCalled())
  const initialReads = reads
  feed.replace([{ ...task, status: 'completed', result: { snapshot: 'committed' } }])
  act(() => feed.malformed())
  expect(await waiting).toEqual({ snapshot: 'committed' })
  expect(feed.connections).toBe(2)
  expect(reads).toBe(initialReads)
})

it.each(['map_initialize', 'self_check', 'archive_hash', 'file_delete'] as const)('applies structured %s progress without per-event or periodic detail reads', async taskType => {
  const task = taskResponse('metadata', { task_type: taskType, progress: 1, progress_details: { kind: taskType, version: 1 } })
  const feed = createTaskEvents([task])
  let reads = 0
  server.use(feed.handler, http.get('*/api/tasks/metadata', () => { reads++; return HttpResponse.json(task) }))
  const view = renderHook(() => useTask('metadata'), { wrapper })
  await waitFor(() => expect(view.result.current.data?.progressDetails?.version).toBe(1))
  await waitFor(() => expect(client.isFetching()).toBe(0))
  const initialReads = reads
  act(() => {
    feed.upsert({ ...task, progress: 20, progress_details: { kind: taskType, version: 2 } })
    feed.upsert({ ...task, progress: 40, progress_details: { kind: taskType, version: 3 } })
  })
  await waitFor(() => expect(view.result.current.data?.progressDetails?.version).toBe(3))
  expect(view.result.current.data?.progress).toBe(40)
  vi.useFakeTimers()
  await act(async () => { await vi.advanceTimersByTimeAsync(10000) })
  expect(reads).toBe(initialReads)
  expect(view.result.current.data?.result).toBeUndefined()
})

it('completes from an included settled result without another detail read', async () => {
  const task = taskResponse('small', { progress: 100 })
  const feed = createTaskEvents([task])
  let reads = 0
  server.use(feed.handler, http.get('*/api/tasks/small', () => { reads++; return HttpResponse.json(task) }))
  const progress = vi.fn()
  const waiting = waitForTaskResult(client, { task_id: 'small' }, { onProgress: progress })
  await waitFor(() => expect(progress).toHaveBeenCalled())
  await waitFor(() => expect(feed.activeConnections).toBe(1))
  const initialReads = reads
  act(() => feed.upsert({ ...task, status: 'completed', result: { snapshot: 'settled' } }))
  expect(await waiting).toEqual({ snapshot: 'settled' })
  expect(reads).toBe(initialReads)
})

it('retains domain snapshots and dismissed prune details for late observers without another connection', async () => {
  const retained = taskResponse('preview', { task_type: 'chunk_prune_preview', status: 'completed', result: { mode: 'regions', dry_run: true } })
  const { taskEvent } = await import('@/test/taskEvents')
  const state = { server_id: 'alpha', preview_task: taskEvent(retained), apply_task: null, preview: null }
  const restoration = { id: 'restore', operation_id: 'restore-task', scope: { kind: 'global' }, status: 'running', targets: [] }
  const feed = createTaskEvents([], { pruneStates: [state], activeRestorations: [restoration] })
  server.use(feed.handler)
  const view = renderHook(useTaskFeed, { wrapper })
  await waitFor(() => expect(view.result.current.connected).toBe(true))
  expect(view.result.current.activeRestorations).toEqual([restoration])
  expect(view.result.current.tasks).toEqual([])
  const detail = renderHook(() => useTask('preview'), { wrapper })
  await waitFor(() => expect(detail.result.current.data?.result).toEqual({ mode: 'regions', dry_run: true }))
  expect(feed.connections).toBe(1)
  act(() => feed.restorations([]))
  await waitFor(() => expect(view.result.current.activeRestorations).toEqual([]))
})

it('does not repeatedly hydrate an excluded prune result on unrelated task progress', async () => {
  const { taskEvent } = await import('@/test/taskEvents')
  const retained = taskResponse('large-preview', { status: 'completed', result: { data: 'x'.repeat(17000) } })
  const feed = createTaskEvents([], { pruneStates: [{ server_id: 'alpha', preview_task: taskEvent(retained), apply_task: null }] })
  let reads = 0
  server.use(feed.handler, http.get('*/api/tasks/large-preview', () => { reads++; return new HttpResponse(null, { status: 503 }) }))
  const view = renderHook(() => useTask('large-preview'), { wrapper })
  await waitFor(() => expect(view.result.current.isError).toBe(true))
  const initialReads = reads
  act(() => { feed.upsert(taskResponse('other', { progress: 20 })); feed.upsert(taskResponse('other', { progress: 40 })) })
  await waitFor(() => expect(client.getQueryData<{ tasks: BackgroundTask[] }>(taskQueryKeys.events())?.tasks[0].progress).toBe(40))
  expect(reads).toBe(initialReads)
  expect(view.result.current.data?.status).toBe('completed')
  expect(view.result.current.resultReady).toBe(false)
})

it('serializes operation batches and reconnects from the last acknowledged cursor', async () => {
  const feed = createTaskEvents()
  server.use(feed.handler)
  const gate = deferred<void>()
  const handled: string[] = []
  const release = subscribeTaskEvents(client, { getOperationCursor: () => 'epoch:0', onOperations: async (changes, signal) => {
    if (changes.next_cursor === 'epoch:1') await gate.promise
    signal.throwIfAborted()
    handled.push(changes.next_cursor)
  } })
  await waitFor(() => expect(feed.connections).toBe(1))
  const change = (cursor: string) => ({ items: [], next_cursor: cursor, reset_required: false, has_more: false, active_count: 0 })
  act(() => { feed.operations(change('epoch:1')); feed.operations(change('epoch:2')) })
  expect(handled).toEqual([])
  expect(client.getQueryData<{ operationCursor: string }>(taskQueryKeys.events())?.operationCursor).toBe('epoch:0')
  await act(async () => { gate.resolve() })
  await waitFor(() => expect(handled).toEqual(['epoch:1', 'epoch:2']))
  act(() => feed.close())
  await waitFor(() => expect(feed.connections).toBe(2), { timeout: 2500 })
  expect(new URL(feed.requests[1]).searchParams.get('operation_cursor')).toBe('epoch:2')
  release()
})

it('removes dismissed list entries without erasing an observed full result', async () => {
  const task = taskResponse('retained', { status: 'completed', result: { snapshot: 'retained-result' } })
  const feed = createTaskEvents([task])
  server.use(feed.handler,
    http.get('*/api/tasks', () => HttpResponse.json({ tasks: [task], total: 1 })),
    http.get('*/api/tasks/retained', () => HttpResponse.json(task)),
  )
  const view = renderHook(() => ({ list: useTasks(), detail: useTask('retained') }), { wrapper })
  await waitFor(() => expect(view.result.current.detail.data?.result).toEqual({ snapshot: 'retained-result' }))
  act(() => feed.remove('retained'))
  await waitFor(() => expect(view.result.current.list.data?.tasks).toEqual([]))
  expect(view.result.current.detail.data?.result).toEqual({ snapshot: 'retained-result' })
  expect(client.getQueryData<BackgroundTask>(taskQueryKeys.detail('retained'))?.status).toBe('completed')
})

it('keeps cancellation acceptance and one hundred percent progress active until cancelled detail settles', async () => {
  const task = taskResponse('cancelling', { progress: 100 })
  const feed = createTaskEvents([task])
  let cancelled = false
  let cancellations = 0
  server.use(feed.handler,
    http.get('*/api/tasks/cancelling', () => HttpResponse.json({ ...task, status: cancelled ? 'cancelled' : 'running', message: cancelled ? '任务已取消' : '正在清理资源' })),
    http.post('*/api/tasks/cancelling/cancel', () => { cancellations++; return HttpResponse.json({}) }),
  )
  const view = renderHook(() => {
    const detail = useTask('cancelling')
    return { task: detail.data, cancel: useCancelTask() }
  }, { wrapper })
  let settled = false
  const waiting = waitForTaskResult<never>(client, { task_id: 'cancelling' }).catch((error: Error) => { settled = true; return error })
  await waitFor(() => expect(view.result.current.task?.status).toBe('running'))
  await act(async () => { await view.result.current.cancel.mutateAsync('cancelling') })
  expect(cancellations).toBe(1)
  expect(settled).toBe(false)
  expect(view.result.current.task?.status).toBe('running')
  cancelled = true
  act(() => feed.upsert({ ...task, status: 'cancelled', message: '任务已取消' }))
  expect((await waiting).message).toBe('任务已取消')
  await waitFor(() => expect(view.result.current.task?.status).toBe('cancelled'))
})

it('retains every task in an unpaginated snapshot beyond one hundred entries', async () => {
  const tasks = Array.from({ length: 125 }, (_, index) => taskResponse(`task-${index}`))
  const feed = createTaskEvents(tasks)
  server.use(feed.handler, http.get('*/api/tasks', () => HttpResponse.json({ tasks, total: tasks.length })))
  const view = renderHook(useTasks, { wrapper })
  await waitFor(() => expect(view.result.current.data?.tasks).toHaveLength(125))
  act(() => feed.upsert(taskResponse('new-task')))
  await waitFor(() => expect(view.result.current.data?.tasks).toHaveLength(126))
  expect(view.result.current.data?.total).toBe(126)
})

it('closes an expired session without reconnecting or leaking late detail into a replacement cache', async () => {
  const gate = deferred<void>()
  let streamRequests = 0
  const expired = vi.fn(() => client.clear())
  window.addEventListener(AUTH_EXPIRED_EVENT, expired)
  server.use(
    http.get('*/api/tasks/events', () => { streamRequests++; return new HttpResponse(null, { status: 401 }) }),
    http.get('*/api/tasks/old', async () => { await gate.promise; return HttpResponse.json(taskResponse('old', { status: 'completed', result: { private: true } })) }),
  )
  try {
    const waiting = waitForTaskResult<never>(client, { task_id: 'old' }).catch((error: Error) => error)
    await waitFor(() => expect(expired).toHaveBeenCalledOnce())
    expect((await waiting).name).toBe('AbortError')
    await act(async () => { gate.resolve() })
    vi.useFakeTimers()
    await vi.advanceTimersByTimeAsync(35000)
    expect(streamRequests).toBe(1)
    expect(client.getQueryCache().getAll()).toEqual([])
  } finally { window.removeEventListener(AUTH_EXPIRED_EVENT, expired); gate.resolve() }
})

it('isolates simultaneous clients and rejects old work when the cache is cleared', async () => {
  const task = taskResponse('old')
  const feed = createTaskEvents([task])
  const oldRead = deferred<void>()
  server.use(feed.handler,
    http.get('*/api/tasks/old', async () => { await oldRead.promise; return HttpResponse.json({ ...task, status: 'completed', result: { old: true } }) }),
    http.get('*/api/tasks', () => HttpResponse.json({ tasks: [task], total: 1 })),
  )
  const other = createTestClient()
  const view = renderHook(useTasks, { wrapper: ({ children }) => <TestProviders client={other}>{children}</TestProviders> })
  try {
    const waiting = waitForTaskResult<never>(client, { task_id: 'old' }).catch((error: Error) => error)
    await waitFor(() => expect(feed.activeConnections).toBe(2))
    act(() => client.clear())
    expect((await waiting).name).toBe('AbortError')
    await waitFor(() => expect(feed.activeConnections).toBe(1))
    await act(async () => { oldRead.resolve() })
    act(() => feed.upsert({ ...task, progress: 85 }))
    await waitFor(() => expect(view.result.current.data?.tasks[0].progress).toBe(85))
    expect(client.getQueryCache().getAll()).toEqual([])
  } finally { oldRead.resolve(); view.unmount(); other.clear() }
})

it('announces a lost stream to detail views and waiters without releasing their guard or polling', async () => {
  const { toast } = await import('sonner')
  const warning = vi.spyOn(toast, 'warning')
  const dismiss = vi.spyOn(toast, 'dismiss')
  const task = taskResponse('connection', { progress: 100 })
  const feed = createTaskEvents([task])
  let reads = 0
  server.use(feed.handler, http.get('*/api/tasks/connection', () => { reads++; return HttpResponse.json(task) }))
  const view = renderHook(() => useTask('connection'), { wrapper })
  const controller = new AbortController()
  let settled = false
  const waiting = waitForTaskResult<never>(client, { task_id: 'connection' }, { signal: controller.signal }).catch((error: Error) => { settled = true; return error })
  await waitFor(() => expect(view.result.current.data?.status).toBe('running'))
  await waitFor(() => expect(feed.activeConnections).toBe(1))
  const initialReads = reads
  act(() => feed.close())
  await waitFor(() => expect(view.result.current.reconnecting).toBe(true))
  expect(view.result.current.isError).toBe(true)
  expect(view.result.current.data?.status).toBe('running')
  expect(settled).toBe(false)
  expect(warning).toHaveBeenCalledWith('暂时无法获取任务状态，正在重新连接', expect.objectContaining({ id: 'task-connection-connection' }))
  await waitFor(() => expect(feed.connections).toBe(2), { timeout: 2500 })
  await waitFor(() => expect(view.result.current.isError).toBe(false))
  expect(dismiss).toHaveBeenCalledWith('task-connection-connection')
  expect(reads).toBe(initialReads)
  controller.abort()
  expect((await waiting).name).toBe('AbortError')
  act(() => feed.upsert({ ...task, status: 'completed' }))
  await waitFor(() => expect(view.result.current.data?.status).toBe('completed'))
  act(() => feed.close())
  await waitFor(() => expect(client.getQueryData<{ connected: boolean }>(taskQueryKeys.events())?.connected).toBe(false))
  expect(view.result.current.isError).toBe(false)
})


it('does not preallocate task detail queries for unobserved snapshot history', async () => {
  const rows = Array.from({ length: 150 }, (_, index) => taskResponse(`history-${index}`, { status: 'completed', result: { preserved: index } }))
  const feed = createTaskEvents(rows)
  server.use(feed.handler, http.get('*/api/tasks', () => HttpResponse.json({ tasks: rows, total: rows.length })))
  const view = renderHook(useTasks, { wrapper })
  await waitFor(() => expect(view.result.current.data?.total).toBe(150))
  expect(client.getQueryCache().findAll({ queryKey: taskQueryKeys.all }).map(query => query.queryKey)).toEqual(expect.arrayContaining([taskQueryKeys.events(), taskQueryKeys.list()]))
  expect(client.getQueryCache().findAll({ queryKey: taskQueryKeys.all })).toHaveLength(2)
})

it('retries the same excluded terminal result after dismissal without resubmitting work', async () => {
  const row = { ...taskResponse('dismissed-result', { status: 'completed' }), result_included: false }
  const feed = createTaskEvents([row])
  let reads = 0
  let writes = 0
  let available = false
  server.use(feed.handler,
    http.get('*/api/tasks/dismissed-result', () => { reads++; return available ? HttpResponse.json({ ...row, result: { preserved: true } }) : new HttpResponse(null, { status: 503 }) }),
    http.post('*/api/*', () => { writes++; return HttpResponse.json({}) }),
  )
  const view = renderHook(() => useTask('dismissed-result'), { wrapper })
  await waitFor(() => expect(view.result.current.resultError).toBeTruthy())
  expect(view.result.current.data?.status).toBe('completed')
  expect(view.result.current.resultReady).toBe(false)
  act(() => feed.remove('dismissed-result'))
  await waitFor(() => expect(client.getQueryData<{ tasks: unknown[] }>(taskQueryKeys.events())?.tasks).toEqual([]))
  available = true
  const before = reads
  await act(async () => { await view.result.current.retryResult() })
  expect(reads).toBe(before + 1)
  await waitFor(() => expect(view.result.current.resultReady).toBe(true))
  expect(view.result.current.data?.result).toEqual({ preserved: true })
  expect(writes).toBe(0)
})

it('retains an authoritative terminal HTTP result when an older running frame arrives during the read', async () => {
  const row = taskResponse('terminal-race')
  const feed = createTaskEvents()
  const gate = deferred<void>()
  let reads = 0
  server.use(feed.handler, http.get('*/api/tasks/terminal-race', async () => {
    reads++
    await gate.promise
    return HttpResponse.json({ ...row, status: 'completed', result: { final: true } })
  }))
  const waiting = waitForTaskResult(client, { task_id: row.task_id })
  await waitFor(() => expect(reads).toBe(1))
  await waitFor(() => expect(feed.activeConnections).toBe(1))
  act(() => feed.upsert(row))
  await waitFor(() => expect(client.getQueryData<BackgroundTask>(taskQueryKeys.detail(row.task_id))?.status).toBe('running'))
  await act(async () => { gate.resolve() })
  expect(await waiting).toEqual({ final: true })
  expect(client.getQueryData<BackgroundTask>(taskQueryKeys.detail(row.task_id))?.status).toBe('completed')
})
