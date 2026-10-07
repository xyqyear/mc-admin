import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterAll, afterEach, beforeAll, beforeEach, expect, it, vi } from 'vitest'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { focusManager, onlineManager, useQuery } from '@tanstack/react-query'
import { Link, Route, Routes } from 'react-router'
import { StrictMode } from 'react'
import { api, queryKeys } from '@/shared/http/api'
import { createTestClient, deferred } from '@/test/http'
import { createOperationFeed } from '@/test/operations'
import { TestProviders } from '@/test/TestProviders'
import { composeOptions } from '@/features/configuration/queries'
import { OperationObserver } from '@/app/operations/OperationObserver'
import type { Operation } from '@/shared/operations/contracts'

const server = setupServer()
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterAll(() => server.close())
let client: ReturnType<typeof createTestClient>
let feed: ReturnType<typeof createOperationFeed>
let compose: string
let reads: number
const operation = (id: string, state = 'running'): Operation => ({ operation_id: id, kind: 'server_rebuild', state, data_changed: false, updated_at: '2026-09-30T00:00:00Z', ended_at: null, resources: [{ kind: 'server', server_id: 'alpha', generation: 1, path: '' }] })
beforeEach(() => {
  client = createTestClient(); feed = createOperationFeed(1); compose = 'old'; reads = 0
  focusManager.setFocused(true)
  server.use(feed.handler, http.get('*/api/servers/alpha/compose', () => { reads++; return HttpResponse.json({ yaml_content: compose, version: compose }) }))
})
afterEach(() => { client.clear(); server.resetHandlers(); onlineManager.setOnline(true); focusManager.setFocused(undefined); vi.useRealTimers(); vi.restoreAllMocks() })
function Editor() {
  const { data } = useQuery(composeOptions('alpha'))
  return <div>配置：{data?.yaml_content}</div>
}
function Shell({ session = 'owner' }: { session?: string }) {
  return <TestProviders client={client}><OperationObserver key={session} sessionId={session} />
    <Link to="/away">离开编辑器</Link><Link to="/">返回编辑器</Link>
    <Routes><Route path="/" element={<Editor />} /><Route path="/away" element={<div>另一页面</div>} /></Routes>
  </TestProviders>
}
async function poll() { await act(async () => { await client.refetchQueries({ queryKey: queryKeys.operations.session('owner'), exact: true }) }) }
async function ready() { await waitFor(() => expect(client.getQueryData(queryKeys.operations.session('owner'))).toBeTruthy()) }
function showObserver() { return render(<TestProviders client={client}><OperationObserver sessionId="owner" /></TestProviders>) }

it.each(['succeeded', 'failed', 'interrupted', 'cancelled'])('refreshes after leaving the submitting page when an operation becomes %s and deduplicates completion', async state => {
  render(<Shell />)
  await screen.findByText('配置：old'); await ready()
  fireEvent.click(screen.getByText('离开编辑器'))
  await screen.findByText('另一页面')
  const invalidate = vi.spyOn(client, 'invalidateQueries')
  compose = 'new'; feed.publish({ ...operation('one', state), data_changed: state !== 'succeeded' })
  await poll()
  expect(client.getQueryState(queryKeys.compose.detail('alpha'))?.isInvalidated).toBe(true)
  const count = invalidate.mock.calls.length
  await poll()
  expect(invalidate).toHaveBeenCalledTimes(count)
  fireEvent.click(screen.getByText('返回编辑器'))
  await screen.findByText('配置：new')
})

it('immediately drains paginated missed changes after reconnect and retains only a checkpoint', async () => {
  render(<Shell />)
  await screen.findByText('配置：old'); await ready()
  onlineManager.setOnline(false)
  feed.publish(...Array.from({ length: 400 }, (_, i) => ({ ...operation(`other-${i}`, 'succeeded'), kind: 'other' })), operation('old-operation', 'failed'))
  compose = 'reconnected'
  await act(async () => { onlineManager.setOnline(true) })
  await screen.findByText('配置：reconnected')
  expect(feed.requests.slice(-3)).toEqual(['1:0', '1:200', '1:400'])
  expect(client.getQueryData(queryKeys.operations.checkpoint('owner'))).toEqual({ cursor: '1:401', active_count: 1 })
  expect(client.getQueryData(queryKeys.operations.session('owner'))).toEqual({ cursor: '1:401', active_count: 1 })
})

it('isolates a remounted session and resets for the next owner', async () => {
  const view = render(<Shell />)
  await screen.findByText('配置：old'); await ready()
  view.unmount(); client.clear()
  compose = 'new-session'
  render(<Shell session="another-owner" />)
  await screen.findByText('配置：new-session')
  await waitFor(() => expect(client.getQueryData(queryKeys.operations.session('another-owner'))).toBeTruthy())
  expect(feed.requests.at(-1)).toBeNull()
  expect(client.getQueryData(queryKeys.operations.checkpoint('owner'))).toBeUndefined()
})

it('retains the cursor on a failed read and resumes without inferring completion', async () => {
  render(<Shell />)
  await screen.findByText('配置：old'); await ready()
  const before = reads
  server.use(http.get('*/api/operations/changes', () => HttpResponse.json({ detail: '暂时不可用' }, { status: 503 })))
  await poll()
  expect(reads).toBe(before)
  expect(client.getQueryData(queryKeys.operations.checkpoint('owner'))).toEqual({ cursor: '1:0', active_count: 1 })
  server.resetHandlers(); server.use(feed.handler, http.get('*/api/servers/alpha/compose', () => HttpResponse.json({ yaml_content: compose, version: compose })))
  feed.publish(operation('one', 'succeeded')); compose = 'recovered'
  await poll()
  await screen.findByText('配置：recovered')
})

it('retains a processed page when the following page fails and merges its invalidations', async () => {
  showObserver(); await ready()
  const invalidate = vi.spyOn(client, 'invalidateQueries')
  feed.publish(...Array.from({ length: 201 }, (_, i) => operation(`completed-${i}`, 'succeeded')))
  let fail = true
  server.use(http.get('*/api/operations/changes', ({ request }) => {
    if (fail && new URL(request.url).searchParams.get('cursor') === '1:200') return HttpResponse.json({}, { status: 503 })
  }))
  await poll()
  expect(client.getQueryData(queryKeys.operations.checkpoint('owner'))).toEqual({ cursor: '1:200', active_count: 1 })
  expect(invalidate.mock.calls.filter(([filters]) => JSON.stringify(filters?.queryKey) === JSON.stringify(queryKeys.compose.detail('alpha')))).toHaveLength(1)
  fail = false; await poll()
  expect(feed.requests.at(-1)).toBe('1:200')
  expect(client.getQueryData(queryKeys.operations.checkpoint('owner'))).toEqual({ cursor: '1:201', active_count: 1 })
})

it('polls an active operation through completion without a page callback', async () => {
  render(<Shell />)
  await screen.findByText('配置：old'); await ready()
  compose = 'polled'; feed.publish(operation('old-operation', 'succeeded'))
  await screen.findByText('配置：polled', {}, { timeout: 4000 })
})

it('resumes after a cancelled second page without repeating the processed page', async () => {
  const view = showObserver(); await ready()
  const release = deferred<void>()
  let pending = false
  server.use(http.get('*/api/operations/changes', async ({ request }) => {
    if (new URL(request.url).searchParams.get('cursor') === '1:200') {
      pending = true
      await release.promise
    }
  }))
  feed.publish(...Array.from({ length: 200 }, (_, i) => operation(`alpha-${i}`, 'succeeded')),
    { ...operation('beta', 'succeeded'), resources: [{ kind: 'server', server_id: 'beta', generation: 1, path: '' }] })
  const invalidate = vi.spyOn(client, 'invalidateQueries')
  const fetching = client.refetchQueries({ queryKey: queryKeys.operations.session('owner'), exact: true })
  await waitFor(() => expect(pending).toBe(true))
  await act(async () => { await client.cancelQueries({ queryKey: queryKeys.operations.session('owner'), exact: true }); await fetching })
  expect(client.getQueryData(queryKeys.operations.checkpoint('owner'))).toEqual({ cursor: '1:200', active_count: 1 })
  view.unmount(); release.resolve()
  server.resetHandlers(); server.use(feed.handler)
  showObserver()
  await waitFor(() => expect(client.getQueryData(queryKeys.operations.session('owner'))).toEqual({ cursor: '1:201', active_count: 1 }))
  expect(invalidate.mock.calls.filter(([filters]) => JSON.stringify(filters?.queryKey) === JSON.stringify(queryKeys.compose.detail('alpha')))).toHaveLength(1)
  expect(invalidate.mock.calls.filter(([filters]) => JSON.stringify(filters?.queryKey) === JSON.stringify(queryKeys.compose.detail('beta')))).toHaveLength(1)
})

it('deduplicates processed changes during StrictMode replay and observer remount', async () => {
  const view = render(<StrictMode><Shell /></StrictMode>)
  await screen.findByText('配置：old'); await ready()
  feed.publish(operation('one', 'succeeded'))
  const invalidate = vi.spyOn(client, 'invalidateQueries')
  await poll()
  view.unmount()
  render(<StrictMode><Shell /></StrictMode>)
  await ready(); await poll()
  expect(invalidate.mock.calls.filter(([filters]) => JSON.stringify(filters?.queryKey) === JSON.stringify(queryKeys.compose.detail('alpha')))).toHaveLength(1)
})

it.each(['restart', 'retention'])('resynchronizes business caches after %s and captures changes during reset refresh', async reason => {
  render(<Shell />)
  await screen.findByText('配置：old'); await ready()
  const previousMapToken = client.getQueryData(queryKeys.map.resetRevision())
  if (reason === 'restart') feed.restart()
  else client.setQueryData(queryKeys.operations.checkpoint('owner'), { cursor: 'expired', active_count: 1 })
  let refreshed = false
  server.use(http.get('*/api/servers/alpha/compose', () => {
    if (!refreshed) { refreshed = true; feed.publish(operation('completed-during-reset', 'failed')) }
    return HttpResponse.json({ yaml_content: compose, version: compose })
  }))
  compose = 'resynchronized'; await poll()
  await screen.findByText('配置：resynchronized')
  expect(client.getQueryData(queryKeys.map.resetRevision())).not.toBe(previousMapToken)
  compose = 'completion after reset'; await poll()
  await screen.findByText('配置：completion after reset')
})

it('rejects a late response after session cache clear without recreating checkpoints', async () => {
  const response = deferred<void>()
  showObserver(); await ready()
  server.use(http.get('*/api/operations/changes', async () => {
    await response.promise
    return HttpResponse.json({ items: [{ ...operation('late', 'succeeded'), sequence: 1 }], next_cursor: '1:1', has_more: false, active_count: 0, reset_required: false })
  }))
  const pending = client.refetchQueries({ queryKey: queryKeys.operations.session('owner'), exact: true })
  await act(async () => { client.clear(); response.resolve(); await pending })
  expect(client.getQueryData(queryKeys.operations.checkpoint('owner'))).toBeUndefined()
  expect(client.getQueryData(queryKeys.operations.session('owner'))).toBeUndefined()
})

it.each(['reset', 'terminal'])('replaces a pending initial business read during %s synchronization', async mode => {
  const captured = deferred<void>()
  const release = deferred<void>()
  let first = true
  if (mode === 'terminal') client.setQueryData(queryKeys.operations.checkpoint('owner'), { cursor: '1:0', active_count: 0 })
  server.use(
    http.get('*/api/servers/alpha/compose', async () => {
      const content = compose
      if (first) { first = false; captured.resolve(); await release.promise }
      return HttpResponse.json({ yaml_content: content, version: content })
    }),
    http.get('*/api/operations/changes', async () => {
      await captured.promise
      compose = 'new'
      return HttpResponse.json({ items: mode === 'reset' ? [] : [{ ...operation('completed', 'succeeded'), sequence: 1 }], next_cursor: '1:1', has_more: false, active_count: 0, reset_required: mode === 'reset' })
    }),
  )
  render(<Shell />)
  await screen.findByText('配置：new')
  expect(client.getQueryData(queryKeys.operations.checkpoint('owner'))).toEqual({ cursor: '1:1', active_count: 0 })
  await act(async () => { release.resolve() })
  expect(screen.getByText('配置：new')).toBeTruthy()
  expect(client.getQueryData(queryKeys.compose.detail('alpha'))).toMatchObject({ yaml_content: 'new' })
})

it.each(['world_restore', 'chunk_prune_apply', 'snapshot_restore', 'file_upload', 'archive_extract'])('refreshes file and world resources after %s partially changes data on another page', async kind => {
  showObserver(); await ready()
  const fileKey = queryKeys.files.list('alpha', '/data'), mapKey = queryKeys.map.regions('alpha', 'world/region'), otherKey = queryKeys.files.list('beta', '/data')
  for (const key of [fileKey, mapKey, otherKey]) client.setQueryData(key, [])
  feed.publish({ ...operation('file-world', 'failed'), kind, data_changed: true })
  await poll()
  expect(client.getQueryState(fileKey)?.isInvalidated).toBe(true)
  expect(client.getQueryState(mapKey)?.isInvalidated).toBe(true)
  expect(client.getQueryState(otherKey)?.isInvalidated).toBe(false)
  const invalidate = vi.spyOn(client, 'invalidateQueries')
  await poll()
  expect(invalidate).not.toHaveBeenCalled()
})

it('refreshes all server files for global file roots without treating archive roots as servers', async () => {
  showObserver(); await ready()
  const alpha = queryKeys.files.list('alpha', '/data'), beta = queryKeys.files.list('beta', '/data'), map = queryKeys.map.regions('beta', 'world/region')
  for (const key of [alpha, beta, map]) client.setQueryData(key, [])
  feed.publish({ ...operation('global', 'failed'), kind: 'snapshot_restore', data_changed: true, resources: [{ kind: 'files', server_id: null, generation: null, path: '' }] })
  await poll()
  for (const key of [alpha, beta, map]) expect(client.getQueryState(key)?.isInvalidated).toBe(true)
  for (const key of [alpha, beta, map]) client.setQueryData(key, [])
  feed.publish({ ...operation('archive', 'succeeded'), kind: 'archive_publish', resources: [{ kind: 'archive', server_id: null, generation: null, path: 'upload.zip' }] })
  await poll()
  for (const key of [alpha, beta, map]) expect(client.getQueryState(key)?.isInvalidated).toBe(false)
})

it('refreshes map initialization across pages without refreshing after tile renders', async () => {
  showObserver(); await ready()
  const status = queryKeys.map.status('alpha'), regions = queryKeys.map.regions('alpha', 'world/region'), unrelated = queryKeys.map.status('beta')
  for (const key of [status, regions, unrelated]) client.setQueryData(key, [])
  feed.publish({ ...operation('initialize', 'failed'), kind: 'map_initialize', data_changed: true })
  await poll()
  expect(client.getQueryState(status)?.isInvalidated).toBe(true)
  expect(client.getQueryState(regions)?.isInvalidated).toBe(true)
  expect(client.getQueryState(unrelated)?.isInvalidated).toBe(false)
  for (const key of [status, regions]) client.setQueryData(key, [])
  feed.publish({ ...operation('tile', 'succeeded'), kind: 'map_render', data_changed: true })
  await poll()
  expect(client.getQueryState(status)?.isInvalidated).toBe(false)
  expect(client.getQueryState(regions)?.isInvalidated).toBe(false)
})

it.each([
  ['server_create', queryKeys.serverInfos.all], ['server_sync', queryKeys.serverStatuses.all],
  ['self_check', queryKeys.selfCheck.all], ['dns_update', queryKeys.dns.all],
  ['archive_publish', queryKeys.archive.all], ['archive_delete', queryKeys.archive.all],
] as const)('refreshes %s resources after an incremental completion', async (kind, key) => {
  showObserver(); await ready()
  client.setQueryData(key, { retained: true })
  feed.publish({ ...operation('finished', 'succeeded'), kind })
  await poll()
  expect(client.getQueryState(key)?.isInvalidated).toBe(true)
})

it('handles a later effective change of the same terminal operation', async () => {
  showObserver(); await ready()
  const key = queryKeys.files.list('alpha', '/data')
  feed.publish({ ...operation('same', 'failed'), kind: 'file_write', data_changed: true })
  await poll(); client.setQueryData(key, [])
  feed.publish({ ...operation('same', 'failed'), kind: 'file_write', data_changed: true, updated_at: '2026-10-01T00:00:00Z' })
  await poll()
  expect(client.getQueryState(key)?.isInvalidated).toBe(true)
})

it('uses active and idle polling, pauses while hidden and immediately resumes on visibility', async () => {
  vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval', 'Date'] })
  const visibility = vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('visible')
  focusManager.setFocused(undefined)
  const response = { items: [], next_cursor: 'timer:0', has_more: false, active_count: 1, reset_required: true }
  const get = vi.spyOn(api, 'get').mockResolvedValue({ data: response })
  showObserver()
  await act(async () => { await Promise.resolve() })
  expect(client.getQueryState(queryKeys.operations.session('owner'))?.error).toBeNull()
  expect(get).toHaveBeenCalled()
  await ready()
  response.reset_required = false
  const initial = get.mock.calls.length
  await act(async () => { await vi.advanceTimersByTimeAsync(2000) })
  await waitFor(() => expect(get).toHaveBeenCalledTimes(initial + 1))
  response.active_count = 0; await poll()
  const idle = get.mock.calls.length
  await act(async () => { await vi.advanceTimersByTimeAsync(29999) })
  expect(get).toHaveBeenCalledTimes(idle)
  await act(async () => { await vi.advanceTimersByTimeAsync(1) })
  await waitFor(() => expect(get).toHaveBeenCalledTimes(idle + 1))
  visibility.mockReturnValue('hidden')
  act(() => { window.dispatchEvent(new Event('visibilitychange')) })
  const hidden = get.mock.calls.length
  await act(async () => { await vi.advanceTimersByTimeAsync(60000) })
  expect(get).toHaveBeenCalledTimes(hidden)
  visibility.mockReturnValue('visible')
  await act(async () => { window.dispatchEvent(new Event('visibilitychange')); await vi.advanceTimersByTimeAsync(1) })
  await waitFor(() => expect(get).toHaveBeenCalledTimes(hidden + 1))
})
