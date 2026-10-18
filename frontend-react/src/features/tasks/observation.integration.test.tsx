import { act, renderHook, waitFor } from '@testing-library/react'
import { afterAll, afterEach, beforeAll, beforeEach, expect, it, vi } from 'vitest'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { AUTH_EXPIRED_EVENT } from '@/shared/http/api'
import { createTestClient, deferred } from '@/test/http'
import { TestProviders } from '@/test/TestProviders'
import { createTaskEvents, taskResponse } from '@/test/taskEvents'
import { useCancelTask, waitForTaskResult } from './commands'
import { taskQueryKeys, useActiveTasks, useTask, useTasks } from './queries'
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
    return { data: task.data, isError: task.isError }
  }, { wrapper })
  let settled = false
  const waiting = waitForTaskResult<{ snapshot: { short_id: string }; skipped_paths: string[] }>(client, { task_id: 'backup' }).then(result => { settled = true; return result })
  void waiting.catch(() => {})
  await waitFor(() => expect(view.result.current.data?.status).toBe('running'))
  completed = true
  act(() => feed.upsert({ ...task, status: 'completed', progress: 100 }))
  await waitFor(() => expect(finalReads).toBe(1))
  expect(view.result.current.data?.status).toBe('running')
  expect(settled).toBe(false)
  await act(async () => { finalRead.resolve() })
  await waitFor(() => expect(view.result.current.isError).toBe(true))
  expect(settled).toBe(false)
  failDetail = false
  await act(async () => { await client.invalidateQueries({ queryKey: taskQueryKeys.detail('backup'), exact: true }) })
  expect(await waiting).toEqual({ snapshot: { short_id: 'real-result' }, skipped_paths: ['protected'] })
  await waitFor(() => expect(view.result.current.data?.status).toBe('completed'))
})

it('recovers through HTTP after EOF and replaces stale lists with the next snapshot without submitting work', async () => {
  const task = taskResponse('backup', { progress: 10 })
  const feed = createTaskEvents([task])
  let current = task
  let reads = 0
  let writes = 0
  server.use(feed.handler,
    http.get('*/api/tasks', () => { reads++; return HttpResponse.json({ tasks: [current], total: 1 }) }),
    http.post('*/api/*', () => { writes++; return HttpResponse.json({}) }),
  )
  const view = renderHook(useTasks, { wrapper })
  await waitFor(() => expect(view.result.current.data?.tasks[0].progress).toBe(10))
  const initialReads = reads
  current = { ...task, progress: 35 }
  feed.replace([{ ...task, progress: 70 }])
  act(() => feed.close())
  await waitFor(() => expect(reads).toBeGreaterThan(initialReads))
  await waitFor(() => expect(view.result.current.data?.tasks[0].progress).toBe(35))
  await waitFor(() => expect(feed.connections).toBe(2), { timeout: 2500 })
  await waitFor(() => expect(view.result.current.data?.tasks[0].progress).toBe(70))
  expect(writes).toBe(0)
})

it('recovers a lost terminal frame even when malformed JSON is followed by keepalive activity', async () => {
  const task = taskResponse('backup')
  const feed = createTaskEvents([task])
  let completed = false
  server.use(feed.handler, http.get('*/api/tasks/backup', () => HttpResponse.json({ ...task,
    status: completed ? 'completed' : 'running', result: completed ? { snapshot: 'committed' } : undefined,
  })))
  const progress = vi.fn()
  const waiting = waitForTaskResult(client, { task_id: 'backup' }, { onProgress: progress })
  void waiting.catch(() => {})
  await waitFor(() => expect(progress).toHaveBeenCalled())
  await waitFor(() => expect(feed.activeConnections).toBe(1))
  completed = true
  act(() => feed.malformed())
  expect(await waiting).toEqual({ snapshot: 'committed' })
})

it.each(['map_initialize', 'self_check'] as const)('coalesces intermediate %s detail reads and retains the newest progress metadata', async taskType => {
  const task = taskResponse('metadata', { task_type: taskType, progress: 1 })
  const feed = createTaskEvents([task])
  const gate = deferred<void>()
  let held = false
  let reads = 0
  let version = 1
  server.use(feed.handler, http.get('*/api/tasks/metadata', async () => {
    reads++
    const captured = version
    if (held) await gate.promise
    return HttpResponse.json({ ...task, result: { version: captured } })
  }))
  const view = renderHook(() => useTask('metadata'), { wrapper })
  await waitFor(() => expect(view.result.current.data?.result?.version).toBe(1))
  await waitFor(() => expect(client.isFetching()).toBe(0))
  const initialReads = reads
  held = true
  version = 2
  act(() => feed.upsert({ ...task, progress: 20 }))
  await waitFor(() => expect(reads).toBe(initialReads + 1))
  expect(view.result.current.data?.result?.version).toBe(1)
  version = 3
  act(() => { feed.upsert({ ...task, progress: 30 }); feed.upsert({ ...task, progress: 40 }) })
  expect(reads).toBe(initialReads + 1)
  await act(async () => { held = false; gate.resolve() })
  await waitFor(() => expect(view.result.current.data?.result?.version).toBe(3))
  expect(view.result.current.data?.progress).toBe(40)
  expect(reads).toBe(initialReads + 2)
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
  act(() => feed.upsert({ ...task, status: 'cancelled' }))
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
