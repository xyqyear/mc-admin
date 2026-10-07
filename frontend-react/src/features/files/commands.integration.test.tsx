import { act, renderHook, waitFor } from '@testing-library/react'
import { afterAll, afterEach, beforeAll, beforeEach, expect, it } from 'vitest'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { createTestClient, deferred } from '@/test/http'
import { TestProviders } from '@/test/TestProviders'
import { queryKeys } from '@/shared/http/api'
import { useCreateFile, useDeleteFile, useBulkDeleteFiles, useUpdateFile, useRenameFile } from './commands'
import { OperationObserver } from '@/app/operations/OperationObserver'
import { createOperationFeed } from '@/test/operations'
import { useMapRevision } from '@/features/world/map/revision'

const server = setupServer()
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterAll(() => server.close())
let client: ReturnType<typeof createTestClient>
beforeEach(() => { client = createTestClient() })
afterEach(() => { client.clear(); server.resetHandlers() })

it('binds writes to the current server and keeps deletion pending until its task completes', async () => {
  const terminal = deferred<void>()
  const writes: unknown[] = []
  let taskReads = 0
  server.use(
    http.post('*/api/servers/:serverId/files/create', async ({ request, params }) => {
      writes.push({ server: params.serverId, body: await request.json() }); return HttpResponse.json({ message: '已创建' })
    }),
    http.delete('*/api/servers/:serverId/files', ({ request, params }) => {
      writes.push({ server: params.serverId, path: new URL(request.url).searchParams.get('path') }); return HttpResponse.json({ task_id: 'deletion' })
    }),
    http.get('*/api/tasks/deletion', async () => {
      taskReads++
      if (taskReads > 1) await terminal.promise
      return HttpResponse.json({ task_id: 'deletion', task_type: 'file_delete', name: '删除', status: taskReads === 1 ? 'running' : 'completed',
        progress: 100, message: '删除', created_at: '2026-10-01T00:00:00Z', result: { deleted: true } })
    }),
  )
  const alpha = queryKeys.files.list('alpha', '/data')
  const beta = queryKeys.files.list('beta', '/data')
  client.setQueryData(alpha, { items: [] }); client.setQueryData(beta, { items: [] })
  const { result, rerender } = renderHook(({ serverId }) => ({ create: useCreateFile(serverId), remove: useDeleteFile(serverId) }), {
    initialProps: { serverId: 'alpha' }, wrapper: ({ children }) => <TestProviders client={client}>{children}</TestProviders>,
  })
  await act(async () => { await result.current.create.mutateAsync({ path: '/data', name: 'a.txt', type: 'file' }) })
  expect(client.getQueryState(alpha)?.isInvalidated).toBe(true)
  expect(client.getQueryState(beta)?.isInvalidated).toBe(false)
  client.setQueryData(alpha, { items: [] })
  rerender({ serverId: 'beta' })
  let deletion!: Promise<unknown>
  act(() => { deletion = result.current.remove.mutateAsync('/data/b.txt') })
  await waitFor(() => expect(taskReads).toBeGreaterThanOrEqual(1))
  expect(result.current.remove.isPending).toBe(true)
  expect(client.getQueryState(beta)?.isInvalidated).toBe(false)
  expect(client.getQueryState(alpha)?.isInvalidated).toBe(false)
  await act(async () => { terminal.resolve(); await deletion })
  await waitFor(() => expect(result.current.remove.isSuccess).toBe(true))
  expect(client.getQueryState(beta)?.isInvalidated).toBe(true)
  expect(client.getQueryState(alpha)?.isInvalidated).toBe(false)
  expect(writes).toEqual([{ server: 'alpha', body: { path: '/data', name: 'a.txt', type: 'file' } }, { server: 'beta', path: '/data/b.txt' }])
})

it('submits one batch and exposes confirmed partial failure without treating acceptance as completion', async () => {
  const terminal = deferred<void>()
  const writes: unknown[] = []
  let reads = 0
  const outcome = { paths: ['a.txt', 'locked'], results: [{ path: 'a.txt', status: 'deleted' }, { path: 'locked', status: 'failed', message: '权限不足' }], deleted: 1, failed: 1, pending: 0 }
  server.use(
    http.post('*/api/servers/alpha/files/delete-batch', async ({ request }) => { writes.push(await request.json()); return HttpResponse.json({ task_id: 'batch' }, { status: 202 }) }),
    http.get('*/api/tasks/batch', async () => {
      const first = ++reads === 1
      if (!first) await terminal.promise
      return HttpResponse.json({ task_id: 'batch', status: first ? 'running' : 'failed', error: first ? null : '部分条目删除失败', result: first ? null : outcome })
    }),
  )
  const { result } = renderHook(() => useBulkDeleteFiles('alpha'), { wrapper: ({ children }) => <TestProviders client={client}>{children}</TestProviders> })
  let deletion!: Promise<unknown>
  act(() => { deletion = result.current.mutateAsync(['/a.txt', '/locked']) })
  await waitFor(() => expect(reads).toBeGreaterThan(0))
  expect(result.current.isPending).toBe(true)
  await act(async () => { terminal.resolve(); expect(await deletion).toEqual(outcome) })
  expect(writes).toEqual([{ paths: ['/a.txt', '/locked'] }])
})

it.each(['file_write', 'file_create', 'file_rename'])('immediately refreshes idle world caches after a synchronous %s command', async kind => {
  const feed = createOperationFeed()
  const path = '/world/region/r.0.0.mca'
  server.use(feed.handler, http.post('*/api/servers/alpha/files/:action', () => {
    feed.publish({ operation_id: 'write', kind, state: 'succeeded', data_changed: true, updated_at: '2026-10-07T00:00:00Z', ended_at: '2026-10-07T00:00:00Z', resources: [{ kind: 'files', server_id: 'alpha', generation: 1, path }] })
    return HttpResponse.json({ message: '已完成' })
  }))
  const { result } = renderHook(() => ({ write: useUpdateFile('alpha'), create: useCreateFile('alpha'), rename: useRenameFile('alpha'), revision: useMapRevision('alpha') }), {
    wrapper: ({ children }) => <TestProviders client={client}><OperationObserver sessionId="owner" />{children}</TestProviders>,
  })
  await waitFor(() => expect(client.getQueryData(queryKeys.operations.session('owner'))).toEqual({ cursor: '1:0', active_count: 0 }))
  await waitFor(() => expect(result.current.revision).toBeDefined())
  const before = result.current.revision
  const map = queryKeys.map.regions('alpha', 'world/region'), other = queryKeys.map.regions('beta', 'world/region')
  client.setQueryData(map, []); client.setQueryData(other, [])
  await act(async () => {
    if (kind === 'file_write') await result.current.write.mutateAsync({ path, content: 'changed' })
    else if (kind === 'file_create') await result.current.create.mutateAsync({ path: '/world/region', name: 'r.0.0.mca', type: 'file' })
    else await result.current.rename.mutateAsync({ old_path: path, new_name: 'r.1.0.mca' })
  })
  await waitFor(() => expect(result.current.revision).not.toBe(before))
  expect(client.getQueryState(map)?.isInvalidated).toBe(true)
  expect(client.getQueryState(other)?.isInvalidated).toBe(false)
  expect(client.getQueryData(queryKeys.operations.checkpoint('owner'))).toEqual({ cursor: '1:1', active_count: 0 })
})

it('restarts pending bootstrap observation when a file command completes after its captured head', async () => {
  const feed = createOperationFeed()
  const captured = deferred<void>(), release = deferred<void>()
  let first = true
  server.use(
    http.get('*/api/operations/changes', async () => {
      if (!first) return
      first = false
      captured.resolve(); await release.promise
      return HttpResponse.json({ items: [], next_cursor: '1:0', has_more: false, active_count: 0, reset_required: true })
    }),
    feed.handler,
    http.post('*/api/servers/alpha/files/create', () => {
      feed.publish({ operation_id: 'created', kind: 'file_create', state: 'succeeded', data_changed: true, updated_at: '2026-10-07T00:00:00Z', ended_at: '2026-10-07T00:00:00Z', resources: [{ kind: 'files', server_id: 'alpha', generation: 1, path: 'world/region/r.0.0.mca' }] })
      return HttpResponse.json({ message: '已创建' })
    }),
  )
  const view = renderHook(() => useCreateFile('alpha'), { wrapper: ({ children }) => <TestProviders client={client}><OperationObserver sessionId="owner" />{children}</TestProviders> })
  await captured.promise
  expect(client.getQueryData(queryKeys.operations.session('owner'))).toBeNull()
  const map = queryKeys.map.regions('alpha', 'world/region')
  client.setQueryData(map, [])
  await act(async () => { await view.result.current.mutateAsync({ path: '/world/region', name: 'r.0.0.mca', type: 'file' }) })
  await waitFor(() => expect(client.getQueryData(queryKeys.operations.checkpoint('owner'))).toEqual({ cursor: '1:1', active_count: 0 }))
  expect(client.getQueryState(map)?.isInvalidated).toBe(true)
  await act(async () => { release.resolve() })
  expect(client.getQueryData(queryKeys.operations.checkpoint('owner'))).toEqual({ cursor: '1:1', active_count: 0 })
})
