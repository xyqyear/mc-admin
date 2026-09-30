import { StrictMode } from 'react'
import { act, renderHook, waitFor } from '@testing-library/react'
import { afterAll, afterEach, beforeAll, beforeEach, expect, it } from 'vitest'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { createTestClient } from '@/test/http'
import { TestProviders } from '@/test/TestProviders'
import { queryKeys } from '@/shared/http/api'
import { taskQueryKeys } from '@/features/tasks/queries'
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

function task(status: string) {
  return { task_id: 'restore-task', task_type: 'snapshot_restore', name: '恢复快照', status,
    progress: status === 'completed' ? 100 : null, message: status === 'completed' ? '恢复完成' : '正在创建安全快照',
    server_id: 'alpha', cancellable: true, created_at: '2026-09-30T00:00:00Z', result: { restoration_id: 'restore-record' } }
}

it('keeps restore blocked through acceptance and failed observations, without resubmitting', async () => {
  const requests: unknown[] = []
  let status = 'pending'
  let disconnected = false
  server.use(
    http.get('*/api/snapshots/restorations/active', () => HttpResponse.json({ total: 0, restorations: [] })),
    http.post('*/api/snapshots/restorations', async ({ request }) => {
      requests.push(await request.json())
      return HttpResponse.json({ task_id: 'restore-task', restoration_id: 'restore-record', skipped_paths: [] }, { status: 202 })
    }),
    http.get('*/api/tasks/restore-task', () => disconnected ? HttpResponse.json({ detail: '连接暂时不可用' }, { status: 503 }) : HttpResponse.json(task(status))),
  )
  const { result } = renderHook(() => useSnapshotOperation(scope), { wrapper })
  await waitFor(() => expect(result.current.busy).toBe(false))
  await act(async () => { await result.current.start('source'); await result.current.start('source') })
  await waitFor(() => expect(result.current.state.message).toBe('正在创建安全快照'))
  expect(result.current.state.active).toBe(true)
  expect(result.current.state.done).toBe(false)
  act(() => result.current.reset())
  expect(result.current.taskId).toBe('restore-task')
  disconnected = true
  await act(async () => { await client.invalidateQueries({ queryKey: taskQueryKeys.all }) })
  await waitFor(() => expect(result.current.state.message).toContain('正在重新连接'))
  expect(result.current.state.active).toBe(true)
  expect(result.current.state.error).toBeNull()
  disconnected = false
  status = 'completed'
  await act(async () => { await client.invalidateQueries({ queryKey: taskQueryKeys.all }) })
  await waitFor(() => expect(result.current.state.done).toBe(true))
  expect(result.current.state.active).toBe(false)
  expect(requests).toEqual([{ scope, source_snapshot_id: 'source', entry_point: 'files' }])
})

it('resumes a pending history after remount and never cancels on navigation', async () => {
  let observations = 0
  let writes = 0
  server.use(
    http.get('*/api/snapshots/restorations/active', () => HttpResponse.json({ total: 1, restorations: [
      { id: 'restore-record', operation_id: 'restore-task', status: 'running', scope },
    ] })),
    http.get('*/api/tasks/restore-task', () => { observations++; return HttpResponse.json(task('running')) }),
    http.post('*/api/*', () => { writes++; return HttpResponse.json({}) }),
  )
  let view = renderHook(() => useSnapshotOperation(scope), { wrapper })
  await waitFor(() => expect(view.result.current.state.active).toBe(true))
  view.unmount()
  client.clear()
  view = renderHook(() => useSnapshotOperation(scope), { wrapper })
  await waitFor(() => expect(view.result.current.state.message).toBe('正在创建安全快照'))
  expect(view.result.current.taskId).toBe('restore-task')
  expect(observations).toBeGreaterThan(0)
  expect(writes).toBe(0)
})

it('keeps create pending until its real task completes', async () => {
  let status = 'running'
  const requests: unknown[] = []
  server.use(
    http.post('*/api/snapshots', async ({ request }) => {
      requests.push(await request.json())
      return HttpResponse.json({ task_id: 'create-task', skipped_paths: [] }, { status: 202 })
    }),
    http.get('*/api/tasks/create-task', () => HttpResponse.json({ ...task(status), task_id: 'create-task', task_type: 'snapshot_create', result: { snapshot: { short_id: 'snapshot' }, skipped_paths: [] } })),
  )
  const { result } = renderHook(() => useCreateSnapshot(), { wrapper })
  act(() => result.current.mutate(scope))
  await waitFor(() => expect(requests).toHaveLength(1))
  expect(result.current.isPending).toBe(true)
  status = 'completed'
  await waitFor(() => expect(result.current.isSuccess).toBe(true), { timeout: 3000 })
  expect(requests).toEqual([{ scope }])
})


it('recovers an active world task without selection and retains it when discovery stops listing it', async () => {
  let listed = true
  let disconnected = false
  let status = 'running'
  let submissions = 0
  server.use(
    http.get('*/api/snapshots/restorations/active', ({ request }) => {
      expect(new URL(request.url).searchParams.get('server_id')).toBe('alpha')
      if (disconnected) return HttpResponse.json({ detail: 'unavailable' }, { status: 503 })
      return HttpResponse.json({ total: listed ? 1 : 0, restorations: listed ? [{ id: 'world-restore', operation_id: 'restore-task', status: 'running', scope: { kind: 'world', server_id: 'alpha', selection: { type: 'regions', regions: [[-1, 0]] } } }] : [] })
    }),
    http.get('*/api/tasks/restore-task', () => disconnected ? HttpResponse.json({}, { status: 503 }) : HttpResponse.json(task(status))),
    http.post('*/api/snapshots/restorations', () => { submissions++; return HttpResponse.json({}) }),
  )
  const { result } = renderHook(() => useSnapshotOperation(null, { serverId: 'alpha', resumeAny: true }), { wrapper })
  await waitFor(() => expect(result.current.taskId).toBe('restore-task'))
  expect(result.current.state.active).toBe(true)
  expect(result.current.state.percent).toBeNull()
  listed = false
  await act(async () => { await client.invalidateQueries({ queryKey: queryKeys.snapshots.all }) })
  expect(result.current.taskId).toBe('restore-task')
  disconnected = true
  await act(async () => { await client.invalidateQueries({ queryKey: taskQueryKeys.all }); await client.invalidateQueries({ queryKey: queryKeys.snapshots.all }) })
  expect(result.current.busy).toBe(true)
  expect(result.current.state.active).toBe(true)
  await act(async () => { await result.current.rollback('world-restore') })
  expect(submissions).toBe(0)
  disconnected = false
  status = 'cancelled'
  await act(async () => { await client.invalidateQueries({ queryKey: taskQueryKeys.all }); await client.invalidateQueries({ queryKey: queryKeys.snapshots.all }) })
  await waitFor(() => expect(result.current.state.active).toBe(false))
  expect(result.current.state.error).toBeTruthy()
})

it('blocks new writes while the initial activity read is unavailable', async () => {
  let readsFail = true
  let submitted = 0
  server.use(
    http.get('*/api/snapshots/restorations/active', () => readsFail ? HttpResponse.json({}, { status: 503 }) : HttpResponse.json({ total: 0, restorations: [] })),
    http.post('*/api/snapshots/restorations', () => { submitted++; return HttpResponse.json({ task_id: 'restore-task', skipped_paths: [] }, { status: 202 }) }),
    http.get('*/api/tasks/restore-task', () => HttpResponse.json(task('pending'))),
  )
  const { result } = renderHook(() => useSnapshotOperation(scope), { wrapper })
  await waitFor(() => expect(result.current.observationMessage).toContain('正在重新连接'))
  await act(async () => { await result.current.start('source') })
  expect(submitted).toBe(0)
  expect(result.current.state.active).toBe(false)
  readsFail = false
  await act(async () => { await client.invalidateQueries({ queryKey: queryKeys.snapshots.all }) })
  await waitFor(() => expect(result.current.busy).toBe(false))
  await act(async () => { await result.current.start('source') })
  expect(submitted).toBe(1)
  expect(result.current.state.active).toBe(true)
})
