import { StrictMode } from 'react'
import { act, renderHook } from '@testing-library/react'
import { afterAll, afterEach, beforeAll, beforeEach, expect, it, vi } from 'vitest'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { focusManager, onlineManager } from '@tanstack/react-query'
import { api, queryKeys } from '@/shared/http/api'
import { createOperationFeed } from '@/test/operations'
import { OperationObserver } from '@/app/operations/OperationObserver'
import type { Operation } from '@/shared/operations/contracts'
import { createTestClient, deferred } from '@/test/http'
import { TestProviders } from '@/test/TestProviders'
import { useActiveRestorations, useRestorationHistory } from './queries'
import { useSnapshotOperation } from './useSnapshotOperation'
import type { ActiveRestorations, SnapshotScope } from './contracts'

const server = setupServer()
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterAll(() => server.close())
let client: ReturnType<typeof createTestClient>
let releaseRequestObserver: (() => void) | undefined
beforeEach(() => {
  client = createTestClient()
  focusManager.setFocused(true)
  vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval', 'Date'] })
})
afterEach(() => {
  client.clear()
  releaseRequestObserver?.()
  releaseRequestObserver = undefined
  server.resetHandlers()
  onlineManager.setOnline(true)
  focusManager.setFocused(undefined)
  vi.useRealTimers()
})
const wrapper = ({ children }: { children: React.ReactNode }) => <TestProviders client={client}>{children}</TestProviders>
const scope: SnapshotScope = { kind: 'paths', server_id: 'alpha', paths: ['plugins'] }
const empty: ActiveRestorations = { total: 0, restorations: [] }
const active: ActiveRestorations = { total: 1, restorations: [{ id: 'restore-record', operation_id: 'restore-task', status: 'running', scope }] }

async function advance(milliseconds: number) {
  await act(async () => { await vi.advanceTimersByTimeAsync(milliseconds) })
}

async function waitFor(check: () => void) {
  // Assertion waits use real time while only the polling clock advances virtually.
  const deadline = performance.now() + 2000
  let failure: unknown
  while (performance.now() < deadline) {
    try { check(); return }
    catch (error) { failure = error }
    await act(async () => { await new Promise(resolve => setTimeout(resolve, 10)) })
  }
  throw failure
}

it('shares one idle polling schedule across staggered consumers and stops after the last one leaves', async () => {
  let reads = 0
  server.use(http.get('*/api/snapshots/restorations/active', () => { reads++; return HttpResponse.json(empty) }))
  const first = renderHook(() => useActiveRestorations('alpha'), { wrapper })
  await waitFor(() => expect(first.result.current.checking).toBe(false))
  expect(reads).toBe(1)
  await advance(10000)
  const second = renderHook(() => useActiveRestorations('alpha'), { wrapper })
  await waitFor(() => expect(second.result.current.checking).toBe(false))
  expect(reads).toBe(2)
  await advance(29999)
  expect(reads).toBe(2)
  await advance(1)
  await waitFor(() => expect(reads).toBe(3))
  await waitFor(() => expect(second.result.current.isFetching).toBe(false))
  first.unmount()
  await advance(30000)
  await waitFor(() => expect(reads).toBe(4))
  await waitFor(() => expect(second.result.current.isFetching).toBe(false))
  second.unmount()
  await advance(60000)
  expect(reads).toBe(4)
})

it('polls active recovery every two seconds and backs off once discovery is empty', async () => {
  let reads = 0
  let body = active
  server.use(http.get('*/api/snapshots/restorations/active', () => { reads++; return HttpResponse.json(body) }))
  const view = renderHook(() => useActiveRestorations('alpha'), { wrapper })
  await waitFor(() => expect(view.result.current.data).toEqual(active))
  await advance(1999)
  expect(reads).toBe(1)
  await advance(1)
  await waitFor(() => expect(reads).toBe(2))
  await waitFor(() => expect(view.result.current.isFetching).toBe(false))
  body = empty
  await advance(2000)
  await waitFor(() => expect(view.result.current.data).toEqual(empty))
  expect(reads).toBe(3)
  await advance(29999)
  expect(reads).toBe(3)
  await advance(1)
  await waitFor(() => expect(reads).toBe(4))
})

it('keeps a re-enabled cached empty discovery blocked until its fresh response arrives', async () => {
  const response = deferred<void>()
  let reads = 0
  let hold = false
  let writes = 0
  server.use(
    http.get('*/api/snapshots/restorations/active', async () => { reads++; if (hold) await response.promise; return HttpResponse.json(empty) }),
    http.post('*/api/snapshots/restorations', () => { writes++; return HttpResponse.json({ task_id: 'restore-task', skipped_paths: [] }, { status: 202 }) }),
    http.get('*/api/tasks/restore-task', () => HttpResponse.json({ task_id: 'restore-task', status: 'running' })),
  )
  const view = renderHook(({ enabled }) => useSnapshotOperation(scope, { enabled }), { wrapper, initialProps: { enabled: true } })
  await waitFor(() => expect(view.result.current.busy).toBe(false))
  view.rerender({ enabled: false })
  await advance(60000)
  expect(reads).toBe(1)
  hold = true
  view.rerender({ enabled: true })
  expect(view.result.current.checking).toBe(true)
  await waitFor(() => expect(reads).toBe(2))
  await act(async () => { await view.result.current.start('source') })
  expect(writes).toBe(0)
  response.resolve()
  await waitFor(() => expect(view.result.current.busy).toBe(false))
  expect(reads).toBe(2)
  await act(async () => { await view.result.current.start('source') })
  expect(writes).toBe(1)
  await waitFor(() => expect(reads).toBe(3))
})

it('checks a cached empty discovery on entry before allowing another recovery', async () => {
  client.setQueryData(queryKeys.snapshots.active('alpha'), empty)
  const response = deferred<void>()
  let reads = 0
  let writes = 0
  server.use(
    http.get('*/api/snapshots/restorations/active', async () => { reads++; await response.promise; return HttpResponse.json(empty) }),
    http.post('*/api/snapshots/restorations', () => { writes++; return HttpResponse.json({}) }),
  )
  const view = renderHook(() => useSnapshotOperation(scope), { wrapper })
  expect(view.result.current.checking).toBe(true)
  await waitFor(() => expect(reads).toBe(1))
  await act(async () => { await view.result.current.start('source') })
  expect(writes).toBe(0)
  response.resolve()
  await waitFor(() => expect(view.result.current.busy).toBe(false))
})

it('isolates polling and fresh-entry guards across independent query clients', async () => {
  for (let update = 0; update < 5; update++) client.setQueryData(queryKeys.snapshots.active('alpha'), empty)
  let held: ReturnType<typeof deferred<void>> | undefined
  let reads = 0
  server.use(http.get('*/api/snapshots/restorations/active', async () => { reads++; await held?.promise; return HttpResponse.json(empty) }))
  const first = renderHook(() => useActiveRestorations('alpha'), { wrapper })
  await waitFor(() => expect(first.result.current.checking).toBe(false))
  const replacement = createTestClient()
  try {
    replacement.setQueryData(queryKeys.snapshots.active('alpha'), empty)
    held = deferred<void>()
    const replacementWrapper = ({ children }: { children: React.ReactNode }) => <TestProviders client={replacement}>{children}</TestProviders>
    const second = renderHook(() => useActiveRestorations('alpha'), { wrapper: replacementWrapper })
    expect(second.result.current.checking).toBe(true)
    await waitFor(() => expect(reads).toBe(2))
    first.unmount()
    held.resolve()
    await waitFor(() => expect(second.result.current.checking).toBe(false))
    await advance(30000)
    await waitFor(() => expect(reads).toBe(3))
    await waitFor(() => expect(second.result.current.isFetching).toBe(false))
    second.unmount()
    await advance(60000)
    expect(reads).toBe(3)
  } finally { replacement.clear() }
})

it('keeps cached discovery errors blocked and retries them on the active cadence', async () => {
  let reads = 0
  let failing = false
  let writes = 0
  server.use(
    http.get('*/api/snapshots/restorations/active', () => { reads++; return failing ? HttpResponse.json({}, { status: 503 }) : HttpResponse.json(empty) }),
    http.post('*/api/snapshots/restorations', () => { writes++; return HttpResponse.json({}) }),
  )
  const view = renderHook(() => useSnapshotOperation(scope), { wrapper })
  await waitFor(() => expect(view.result.current.busy).toBe(false))
  failing = true
  await act(async () => { await client.invalidateQueries({ queryKey: queryKeys.snapshots.active('alpha') }) })
  await waitFor(() => expect(view.result.current.observationMessage).toContain('正在重新连接'))
  expect(view.result.current.busy).toBe(true)
  await act(async () => { await view.result.current.start('source') })
  expect(writes).toBe(0)
  expect(reads).toBe(2)
  failing = false
  await advance(2000)
  await waitFor(() => expect(view.result.current.busy).toBe(false))
  expect(reads).toBe(3)
})

it('isolates server schedules and cancels an abandoned paginated discovery', async () => {
  const held = deferred<void>()
  const requests: string[] = []
  let abandonedSignal: AbortSignal | undefined
  const requestObserver = api.interceptors.request.use(config => {
    if (config.url === '/snapshots/restorations/active' && config.params?.server_id === 'alpha') {
      abandonedSignal = config.signal as AbortSignal
    }
    return config
  })
  releaseRequestObserver = () => api.interceptors.request.eject(requestObserver)
  server.use(http.get('*/api/snapshots/restorations/active', async ({ request }) => {
    const url = new URL(request.url)
    const name = url.searchParams.get('server_id')!
    const offset = url.searchParams.get('offset')!
    requests.push(`${name}:${offset}`)
    if (name === 'beta') return HttpResponse.json(empty)
    await held.promise
    return HttpResponse.json({ ...active, total: 201 })
  }))
  const view = renderHook(({ serverId }) => useActiveRestorations(serverId), { wrapper, initialProps: { serverId: 'alpha' } })
  await waitFor(() => expect(requests).toEqual(['alpha:0']))
  view.rerender({ serverId: 'beta' })
  await waitFor(() => expect(view.result.current.checking).toBe(false))
  expect(abandonedSignal?.aborted).toBe(true)
  expect(client.getQueryState(queryKeys.snapshots.active('alpha'))?.fetchStatus).toBe('idle')
  held.resolve()
  await advance(30000)
  await waitFor(() => expect(requests).toEqual(['alpha:0', 'beta:0', 'beta:0']))
  expect(client.getQueryData(queryKeys.snapshots.active('alpha'))).toBeUndefined()
})

it('retains one schedule through StrictMode replay and refreshes on focus and reconnect', async () => {
  let reads = 0
  server.use(http.get('*/api/snapshots/restorations/active', () => { reads++; return HttpResponse.json(empty) }))
  const strictWrapper = ({ children }: { children: React.ReactNode }) => <StrictMode><TestProviders client={client}>{children}</TestProviders></StrictMode>
  const view = renderHook(() => useActiveRestorations('alpha'), { wrapper: strictWrapper })
  await waitFor(() => expect(view.result.current.checking).toBe(false))
  const initial = reads
  await advance(30000)
  await waitFor(() => expect(reads).toBe(initial + 1))
  await waitFor(() => expect(view.result.current.isFetching).toBe(false))
  act(() => focusManager.setFocused(false))
  await advance(30000)
  expect(reads).toBe(initial + 1)
  act(() => focusManager.setFocused(true))
  await waitFor(() => expect(reads).toBe(initial + 2))
  await waitFor(() => expect(view.result.current.isFetching).toBe(false))
  act(() => onlineManager.setOnline(false))
  act(() => onlineManager.setOnline(true))
  await waitFor(() => expect(reads).toBe(initial + 3))
  view.unmount()
  await advance(60000)
  expect(reads).toBe(initial + 3)
})

it('refreshes running restoration history on entry and invalidation without periodic repository reads', async () => {
  client.setDefaultOptions({ queries: { retry: false, gcTime: Infinity, staleTime: 300000 } })
  let reads = 0
  server.use(http.get('*/api/snapshots/restorations', () => { reads++; return HttpResponse.json(active) }))
  const first = renderHook(() => useRestorationHistory('alpha'), { wrapper })
  await waitFor(() => expect(first.result.current.isSuccess).toBe(true))
  await advance(60000)
  expect(reads).toBe(1)
  first.unmount()
  const second = renderHook(({ enabled }) => useRestorationHistory('alpha', 0, enabled), { wrapper, initialProps: { enabled: true } })
  await waitFor(() => expect(reads).toBe(2))
  await waitFor(() => expect(second.result.current.isFetching).toBe(false))
  second.rerender({ enabled: false })
  await advance(60000)
  expect(reads).toBe(2)
  second.rerender({ enabled: true })
  await waitFor(() => expect(reads).toBe(3))
  await waitFor(() => expect(second.result.current.isFetching).toBe(false))
  await act(async () => { await client.invalidateQueries({ queryKey: queryKeys.snapshots.all }) })
  expect(reads).toBe(4)
  await advance(60000)
  expect(reads).toBe(4)
})

it('refreshes recovery discovery and history when an operation completes on another page', async () => {
  let body = active
  let historyReads = 0
  const feed = createOperationFeed(1)
  let operation: Operation = {
    operation_id: 'restore-task', kind: 'snapshot_restore', state: 'running',
    data_changed: false, updated_at: '2026-10-07T00:00:00Z', ended_at: null,
    resources: [{ kind: 'files', server_id: 'alpha', generation: 1, path: 'plugins' }],
  }
  server.use(
    http.get('*/api/snapshots/restorations/active', () => HttpResponse.json(body)),
    http.get('*/api/snapshots/restorations', () => { historyReads++; return HttpResponse.json(active) }),
    feed.handler,
  )
  const operationWrapper = ({ children }: { children: React.ReactNode }) => <TestProviders client={client}><OperationObserver sessionId="owner" />{children}</TestProviders>
  const view = renderHook(() => ({ discovery: useActiveRestorations('alpha'), history: useRestorationHistory('alpha') }), { wrapper: operationWrapper })
  await waitFor(() => expect(view.result.current.discovery.data).toEqual(active))
  await waitFor(() => expect(view.result.current.history.isSuccess).toBe(true))
  await waitFor(() => expect(client.getQueryData(queryKeys.operations.session('owner'))).toEqual({ cursor: '1:0', active_count: 1 }))
  await waitFor(() => expect(view.result.current.history.isFetching).toBe(false))
  const initialReads = historyReads
  body = empty
  operation = { ...operation, state: 'succeeded', data_changed: true, ended_at: '2026-10-07T00:00:01Z' }; feed.publish(operation)
  await act(async () => { await client.invalidateQueries({ queryKey: queryKeys.operations.all }) })
  await waitFor(() => expect(view.result.current.discovery.data).toEqual(empty))
  await waitFor(() => expect(historyReads).toBe(initialReads + 1))
  await advance(60000)
  expect(historyReads).toBe(initialReads + 1)
})
