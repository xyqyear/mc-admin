import { StrictMode } from 'react'
import { act, renderHook, waitFor } from '@testing-library/react'
import { afterAll, afterEach, beforeAll, beforeEach, expect, it, vi } from 'vitest'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { queryKeys } from '@/shared/http/api'
import { OperationObserver } from '@/app/operations/OperationObserver'
import { createTaskEvents, taskResponse } from '@/test/taskEvents'
import { createTestClient } from '@/test/http'
import { TestProviders } from '@/test/TestProviders'
import { useActiveRestorations, useRestorationHistory } from './queries'
import { useSnapshotOperation } from './useSnapshotOperation'
import type { ActiveRestorations, SnapshotScope } from './contracts'

const server = setupServer()
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterAll(() => server.close())
let client: ReturnType<typeof createTestClient>
beforeEach(() => { client = createTestClient() })
afterEach(() => { client.clear(); server.resetHandlers(); vi.useRealTimers() })
const wrapper = ({ children }: { children: React.ReactNode }) => <TestProviders client={client}>{children}</TestProviders>
const scope: SnapshotScope = { kind: 'paths', server_id: 'alpha', paths: ['plugins'] }
const empty: ActiveRestorations = { total: 0, restorations: [] }
const row = { id: 'restore-record', operation_id: 'restore-task', status: 'running', scope, targets: [{ server_id: 'alpha', generation: 1 }] }
const active: ActiveRestorations = { total: 1, restorations: [{ id: row.id, operation_id: row.operation_id, status: 'running', scope }] }

async function waitForHistory(check: () => void) {
  const deadline = performance.now() + 2000
  let failure: unknown
  while (performance.now() < deadline) {
    try { check(); return }
    catch (error) { failure = error }
    await act(async () => { await new Promise(resolve => setTimeout(resolve, 10)) })
  }
  throw failure
}

it('shares one connection with late consumers and closes it after the last observer leaves', async () => {
  const feed = createTaskEvents([], { activeRestorations: [row] })
  let discoveryReads = 0
  server.use(feed.handler, http.get('*/api/snapshots/restorations/active', () => { discoveryReads++; return HttpResponse.json(empty) }))
  const first = renderHook(() => useActiveRestorations('alpha'), { wrapper })
  await waitFor(() => expect(first.result.current.data).toEqual(active))
  const second = renderHook(() => useActiveRestorations('alpha'), { wrapper })
  await waitFor(() => expect(second.result.current.checking).toBe(false))
  expect(second.result.current.data).toEqual(active)
  expect(feed.connections).toBe(1)
  first.unmount()
  expect(feed.activeConnections).toBe(1)
  act(() => feed.restorations([]))
  await waitFor(() => expect(second.result.current.data).toEqual(empty))
  second.unmount()
  await waitFor(() => expect(feed.activeConnections).toBe(0))
  expect(discoveryReads).toBe(0)
})

it('discovers every streamed restoration and filters global targets for each server', async () => {
  const rows = Array.from({ length: 205 }, (_, index) => ({ ...row, id: `restore-${index}`, operation_id: `task-${index}` }))
  const global = { ...row, id: 'global', operation_id: 'global-task', scope: { kind: 'global' }, targets: [{ server_id: 'beta', generation: 2 }] }
  const feed = createTaskEvents([], { activeRestorations: [...rows, global] })
  server.use(feed.handler)
  const view = renderHook(({ serverId }) => useActiveRestorations(serverId), { wrapper, initialProps: { serverId: 'alpha' } })
  await waitFor(() => expect(view.result.current.data?.total).toBe(205))
  view.rerender({ serverId: 'beta' })
  await waitFor(() => expect(view.result.current.data?.restorations).toEqual([{ id: 'global', operation_id: 'global-task', status: 'running', scope: { kind: 'global' } }]))
  expect(feed.connections).toBe(1)
  view.rerender({ serverId: 'other' })
  await waitFor(() => expect(view.result.current.data).toEqual(empty))
})

it('keeps cached empty discovery blocked until a valid initial domain snapshot arrives', async () => {
  client.setQueryData(queryKeys.snapshots.active('alpha'), empty)
  const feed = createTaskEvents([], { activeRestorations: [{}] })
  let writes = 0
  server.use(feed.handler,
    http.post('*/api/snapshots/restorations', () => { writes++; return HttpResponse.json({ task_id: 'restore-task', skipped_paths: [] }, { status: 202 }) }),
    http.get('*/api/tasks/restore-task', () => HttpResponse.json(taskResponse('restore-task', { status: 'pending' }))),
  )
  const view = renderHook(() => useSnapshotOperation(scope), { wrapper })
  await waitFor(() => expect(feed.activeConnections).toBe(1))
  expect(view.result.current.checking).toBe(true)
  await act(async () => { await view.result.current.start('source') })
  expect(writes).toBe(0)
  act(() => feed.restorations([]))
  await waitFor(() => expect(view.result.current.busy).toBe(false))
  await act(async () => { await view.result.current.start('source') })
  expect(writes).toBe(1)
})

it('requires fresh discovery when re-enabled after the last stream consumer leaves', async () => {
  const feed = createTaskEvents()
  server.use(feed.handler)
  const view = renderHook(({ enabled }) => useActiveRestorations('alpha', enabled), { wrapper, initialProps: { enabled: true } })
  await waitFor(() => expect(view.result.current.checking).toBe(false))
  view.rerender({ enabled: false })
  await waitFor(() => expect(feed.activeConnections).toBe(0))
  feed.restorations([{}])
  view.rerender({ enabled: true })
  await waitFor(() => expect(feed.connections).toBe(2))
  expect(view.result.current.checking).toBe(true)
  act(() => feed.restorations([row]))
  await waitFor(() => expect(view.result.current.data).toEqual(active))
  expect(view.result.current.checking).toBe(false)
})

it('retains active discovery and blocks writes while disconnected until a successful reconnect snapshot', async () => {
  const feed = createTaskEvents([], { activeRestorations: [row] })
  let writes = 0
  server.use(feed.handler, http.post('*/api/snapshots/restorations', () => { writes++; return HttpResponse.json({}) }))
  const view = renderHook(() => useSnapshotOperation(scope), { wrapper })
  await waitFor(() => expect(view.result.current.taskId).toBe('restore-task'))
  act(() => feed.close())
  await waitFor(() => expect(view.result.current.observationMessage).toContain('正在重新连接'))
  expect(view.result.current.busy).toBe(true)
  await act(async () => { await view.result.current.start('source') })
  expect(writes).toBe(0)
  feed.restorations([])
  await waitFor(() => expect(feed.connections).toBe(2), { timeout: 3000 })
  await waitFor(() => expect(view.result.current.checking).toBe(false))
  expect(view.result.current.taskId).toBe('restore-task')
  expect(view.result.current.state.active).toBe(true)
})

it('isolates independent clients and ignores events from a cleared session', async () => {
  const oldFeed = createTaskEvents([], { activeRestorations: [row] })
  server.use(oldFeed.handler)
  const first = renderHook(() => useActiveRestorations('alpha'), { wrapper })
  await waitFor(() => expect(first.result.current.data).toEqual(active))
  const replacement = createTestClient()
  const newFeed = createTaskEvents([], { activeRestorations: [{}] })
  server.use(newFeed.handler)
  const replacementWrapper = ({ children }: { children: React.ReactNode }) => <TestProviders client={replacement}>{children}</TestProviders>
  try {
    const second = renderHook(() => useActiveRestorations('alpha'), { wrapper: replacementWrapper })
    await waitFor(() => expect(newFeed.activeConnections).toBe(1))
    expect(second.result.current.checking).toBe(true)
    first.unmount()
    client.clear()
    await waitFor(() => expect(oldFeed.activeConnections).toBe(0))
    act(() => oldFeed.restorations([row]))
    expect(second.result.current.checking).toBe(true)
    act(() => newFeed.restorations([]))
    await waitFor(() => expect(second.result.current.data).toEqual(empty))
    expect(client.getQueryCache().getAll()).toHaveLength(0)
    second.unmount()
  } finally { replacement.clear() }
})

it('retains one live subscription through StrictMode replay and closes it on unmount', async () => {
  const feed = createTaskEvents()
  server.use(feed.handler)
  const strictWrapper = ({ children }: { children: React.ReactNode }) => <StrictMode><TestProviders client={client}>{children}</TestProviders></StrictMode>
  const view = renderHook(() => useActiveRestorations('alpha'), { wrapper: strictWrapper })
  await waitFor(() => expect(view.result.current.checking).toBe(false))
  expect(feed.activeConnections).toBe(1)
  const initial = feed.connections
  view.rerender()
  act(() => feed.restorations([row]))
  await waitFor(() => expect(view.result.current.data).toEqual(active))
  expect(feed.connections).toBe(initial)
  view.unmount()
  await waitFor(() => expect(feed.activeConnections).toBe(0))
})

it('refreshes restoration history on entry and invalidation without periodic repository reads', async () => {
  vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
  client.setDefaultOptions({ queries: { retry: false, gcTime: Infinity, staleTime: 300000 } })
  let reads = 0
  server.use(http.get('*/api/snapshots/restorations', () => { reads++; return HttpResponse.json(active) }))
  const first = renderHook(() => useRestorationHistory('alpha'), { wrapper })
  await waitForHistory(() => expect(first.result.current.isSuccess).toBe(true))
  await act(async () => { await vi.advanceTimersByTimeAsync(60000) })
  expect(reads).toBe(1)
  first.unmount()
  const second = renderHook(({ enabled }) => useRestorationHistory('alpha', 0, enabled), { wrapper, initialProps: { enabled: true } })
  await waitForHistory(() => expect(reads).toBe(2))
  await waitForHistory(() => expect(second.result.current.isFetching).toBe(false))
  second.rerender({ enabled: false })
  second.rerender({ enabled: true })
  await waitForHistory(() => expect(reads).toBe(3))
  await waitForHistory(() => expect(second.result.current.isFetching).toBe(false))
  await act(async () => { await client.invalidateQueries({ queryKey: queryKeys.snapshots.all }) })
  expect(reads).toBe(4)
  await act(async () => { await vi.advanceTimersByTimeAsync(60000) })
  expect(reads).toBe(4)
})

it('updates discovery and refreshes history when an operation settles on another page', async () => {
  const feed = createTaskEvents([], { activeRestorations: [row] })
  let historyReads = 0
  server.use(feed.handler, http.get('*/api/snapshots/restorations', () => { historyReads++; return HttpResponse.json(active) }))
  const operationWrapper = ({ children }: { children: React.ReactNode }) => <TestProviders client={client}><OperationObserver sessionId="owner" />{children}</TestProviders>
  const view = renderHook(() => ({ discovery: useActiveRestorations('alpha'), history: useRestorationHistory('alpha') }), { wrapper: operationWrapper })
  await waitFor(() => expect(view.result.current.discovery.data).toEqual(active))
  await waitFor(() => expect(view.result.current.history.isSuccess).toBe(true))
  act(() => feed.operations({ items: [], next_cursor: 'initial', active_count: 1, has_more: false, reset_required: true }))
  await waitFor(() => expect(client.getQueryData(queryKeys.operations.checkpoint('owner'))).toEqual({ cursor: 'initial', active_count: 1 }))
  await waitFor(() => expect(view.result.current.history.isFetching).toBe(false))
  const initialReads = historyReads
  act(() => {
    feed.restorations([])
    feed.operations({ items: [{ sequence: 1, operation_id: 'restore-task', kind: 'snapshot_restore', state: 'succeeded', data_changed: true,
      updated_at: '2026-10-07T00:00:01Z', ended_at: '2026-10-07T00:00:01Z', resources: [{ kind: 'files', server_id: 'alpha', generation: 1, path: 'plugins' }] }],
    next_cursor: 'settled', active_count: 0, has_more: false, reset_required: false })
  })
  await waitFor(() => expect(view.result.current.discovery.data).toEqual(empty))
  await waitFor(() => expect(historyReads).toBe(initialReads + 1))
  expect(feed.connections).toBe(1)
})
