import { StrictMode } from 'react'
import { act, renderHook, waitFor } from '@testing-library/react'
import { afterAll, afterEach, beforeAll, beforeEach, expect, it } from 'vitest'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { createTaskEvents, taskEventsUnavailable, taskResponse } from '@/test/taskEvents'
import { createTestClient } from '@/test/http'
import { TestProviders } from '@/test/TestProviders'
import type { BackgroundTaskStatus } from '@/features/tasks/contracts'
import { useCreateSnapshot, useSnapshotOperation } from './commands'
import type { SnapshotScope } from './contracts'

const server = setupServer()
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterAll(() => server.close())
let client: ReturnType<typeof createTestClient>
beforeEach(() => { client = createTestClient() })
afterEach(() => { client.clear(); server.resetHandlers() })
const wrapper = ({ children }: { children: React.ReactNode }) => <StrictMode><TestProviders client={client}>{children}</TestProviders></StrictMode>
const scope: SnapshotScope = { kind: 'paths', server_id: 'alpha', paths: ['plugins'] }
const restoration = { id: 'restore-record', operation_id: 'restore-task', status: 'running', scope, targets: [{ server_id: 'alpha', generation: 1 }] }

function task(status: BackgroundTaskStatus) {
  return taskResponse('restore-task', { task_type: 'snapshot_restore', name: '恢复快照', status,
    progress: status === 'completed' ? 100 : null, message: status === 'completed' ? '恢复完成' : '正在创建安全快照',
    result: { restoration_id: 'restore-record' } })
}

it('keeps restore blocked through acceptance and disconnection without resubmitting', async () => {
  const feed = createTaskEvents()
  const requests: unknown[] = []
  server.use(feed.handler,
    http.post('*/api/snapshots/restorations', async ({ request }) => {
      requests.push(await request.json())
      feed.upsert(task('pending'))
      return HttpResponse.json({ task_id: 'restore-task', restoration_id: 'restore-record', skipped_paths: [] }, { status: 202 })
    }),
    http.get('*/api/tasks/restore-task', () => HttpResponse.json(task('pending'))),
  )
  const { result } = renderHook(() => useSnapshotOperation(scope), { wrapper })
  await waitFor(() => expect(result.current.busy).toBe(false))
  await act(async () => { await result.current.start('source'); await result.current.start('source') })
  await waitFor(() => expect(result.current.state.message).toBe('正在创建安全快照'))
  expect(result.current.state.active).toBe(true)
  expect(result.current.state.done).toBe(false)
  act(() => {
    result.current.reset()
    feed.upsert({ ...task('running'), progress: 100 })
  })
  await waitFor(() => expect(result.current.state.percent).toBe(100))
  expect(result.current.taskId).toBe('restore-task')
  expect(result.current.state.done).toBe(false)
  act(() => feed.close())
  await waitFor(() => expect(result.current.observationMessage).toContain('正在重新连接'))
  expect(result.current.state.active).toBe(true)
  expect(result.current.state.error).toBeNull()
  await act(async () => { await result.current.start('source') })
  feed.replace([task('completed')])
  await waitFor(() => expect(result.current.state.done).toBe(true), { timeout: 3000 })
  expect(result.current.state.active).toBe(false)
  expect(requests).toEqual([{ scope, source_snapshot_id: 'source', entry_point: 'files' }])
})

it('resumes pending history after remount without cancelling on navigation', async () => {
  const feed = createTaskEvents([task('running')], { activeRestorations: [restoration] })
  let writes = 0
  server.use(feed.handler,
    http.get('*/api/tasks/restore-task', () => HttpResponse.json(task('running'))),
    http.post('*/api/*', () => { writes++; return HttpResponse.json({}) }),
  )
  let view = renderHook(() => useSnapshotOperation(scope), { wrapper })
  await waitFor(() => expect(view.result.current.state.active).toBe(true))
  view.unmount()
  client.clear()
  view = renderHook(() => useSnapshotOperation(scope), { wrapper })
  await waitFor(() => expect(view.result.current.state.message).toBe('正在创建安全快照'))
  expect(view.result.current.taskId).toBe('restore-task')
  expect(writes).toBe(0)
  expect(feed.activeConnections).toBe(1)
})

it('keeps create pending at 100 percent until its real terminal event', async () => {
  const feed = createTaskEvents()
  const requests: unknown[] = []
  const running = taskResponse('create-task', { progress: 100, message: '正在收尾', result: { snapshot: { short_id: 'snapshot' }, skipped_paths: [] } })
  let reads = 0
  server.use(feed.handler,
    http.post('*/api/snapshots', async ({ request }) => {
      requests.push(await request.json())
      feed.upsert(running)
      return HttpResponse.json({ task_id: 'create-task', skipped_paths: [] }, { status: 202 })
    }),
    http.get('*/api/tasks/create-task', () => { reads++; return HttpResponse.json(running) }),
  )
  const { result } = renderHook(() => useCreateSnapshot(), { wrapper })
  act(() => result.current.mutate(scope))
  await waitFor(() => expect(result.current.task?.progress).toBe(100))
  expect(result.current.isPending).toBe(true)
  expect(result.current.isSuccess).toBe(false)
  const initialReads = reads
  act(() => feed.upsert({ ...running, status: 'completed' }))
  await waitFor(() => expect(result.current.isSuccess).toBe(true))
  expect(result.current.data).toEqual(running.result)
  expect(reads).toBe(initialReads)
  expect(requests).toEqual([{ scope }])
})

it('retains an active world task after discovery removes it and waits for cancelled settlement', async () => {
  const world: SnapshotScope = { kind: 'world', server_id: 'alpha', selection: { type: 'regions', regions: [[-1, 0]] } }
  const feed = createTaskEvents([task('running')], { activeRestorations: [{ ...restoration, scope: world }] })
  let submissions = 0
  server.use(feed.handler,
    http.get('*/api/tasks/restore-task', () => HttpResponse.json(task('running'))),
    http.post('*/api/snapshots/restorations', () => { submissions++; return HttpResponse.json({}) }),
  )
  const { result } = renderHook(() => useSnapshotOperation(null, { serverId: 'alpha', resumeAny: true }), { wrapper })
  await waitFor(() => expect(result.current.taskId).toBe('restore-task'))
  expect(result.current.state.active).toBe(true)
  expect(result.current.state.percent).toBeNull()
  act(() => feed.restorations([]))
  expect(result.current.taskId).toBe('restore-task')
  act(() => feed.close())
  await waitFor(() => expect(result.current.checking).toBe(true))
  expect(result.current.busy).toBe(true)
  expect(result.current.state.active).toBe(true)
  await act(async () => { await result.current.rollback('world-restore') })
  expect(submissions).toBe(0)
  feed.replace([task('cancelled')])
  await waitFor(() => expect(result.current.state.active).toBe(false), { timeout: 3000 })
  expect(result.current.state.error).toBeTruthy()
})

it('blocks new writes while initial streamed discovery is unavailable', async () => {
  const feed = createTaskEvents()
  let submitted = 0
  server.use(taskEventsUnavailable,
    http.post('*/api/snapshots/restorations', () => {
      submitted++
      feed.upsert(task('pending'))
      return HttpResponse.json({ task_id: 'restore-task', skipped_paths: [] }, { status: 202 })
    }),
    http.get('*/api/tasks/restore-task', () => HttpResponse.json(task('pending'))),
  )
  const { result } = renderHook(() => useSnapshotOperation(scope), { wrapper })
  expect(result.current.busy).toBe(true)
  await act(async () => { await result.current.start('source') })
  expect(submitted).toBe(0)
  expect(result.current.state.active).toBe(false)
  server.use(feed.handler)
  await waitFor(() => expect(result.current.busy).toBe(false), { timeout: 3000 })
  await act(async () => { await result.current.start('source') })
  expect(submitted).toBe(1)
  expect(result.current.state.active).toBe(true)
})

it('retries a completed restore result after dismissal without repeating the restore', async () => {
  const feed = createTaskEvents()
  let submissions = 0
  let reads = 0
  let readable = false
  server.use(feed.handler,
    http.post('*/api/snapshots/restorations', () => {
      submissions++
      feed.upsert(task('running'))
      return HttpResponse.json({ task_id: 'restore-task', restoration_id: 'restore-record', skipped_paths: [] }, { status: 202 })
    }),
    http.get('*/api/tasks/restore-task', () => {
      reads++
      return readable ? HttpResponse.json(task('completed')) : HttpResponse.json({ detail: '暂时不可用' }, { status: 503 })
    }),
  )
  const { result } = renderHook(() => useSnapshotOperation(scope), { wrapper })
  await waitFor(() => expect(result.current.busy).toBe(false))
  await act(async () => { await result.current.start('source') })
  await waitFor(() => expect(result.current.state.active).toBe(true))
  act(() => feed.upsert({ ...task('completed'), result_included: false }))
  await waitFor(() => expect(result.current.state.message).toContain('结果读取失败'))
  expect(result.current.busy).toBe(true)
  expect(result.current.state.done).toBe(false)
  act(() => feed.remove('restore-task'))
  const failedReads = reads
  readable = true
  await act(async () => { await result.current.retryResult() })
  await waitFor(() => expect(result.current.state.done).toBe(true))
  expect(result.current.busy).toBe(false)
  expect(reads).toBe(failedReads + 1)
  expect(submissions).toBe(1)
})
