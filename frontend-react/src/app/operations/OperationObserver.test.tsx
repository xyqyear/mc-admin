import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterAll, afterEach, beforeAll, beforeEach, expect, it, vi } from 'vitest'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { useQuery } from '@tanstack/react-query'
import { Link, Route, Routes } from 'react-router'
import { StrictMode } from 'react'
import { queryKeys } from '@/shared/http/api'
import { createTestClient, deferred } from '@/test/http'
import { createOperationFeed } from '@/test/operations'
import { TestProviders } from '@/test/TestProviders'
import { composeOptions } from '@/features/configuration/queries'
import { OperationObserver } from './OperationObserver'
import type { Operation } from '@/shared/operations/contracts'

const server = setupServer()
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterAll(() => server.close())
let client: ReturnType<typeof createTestClient>
let feed: ReturnType<typeof createOperationFeed>
let compose: string
let pollingReads: number
const operation = (id: string, state = 'running'): Operation => ({ operation_id: id, kind: 'server_rebuild', state, data_changed: false, updated_at: '2026-09-30T00:00:00Z', ended_at: null, resources: [{ kind: 'server', server_id: 'alpha', generation: 1, path: '' }] })
beforeEach(() => {
  client = createTestClient(); feed = createOperationFeed(1); compose = 'old'; pollingReads = 0
  server.use(feed.handler,
    http.get('*/api/operations/changes', () => { pollingReads++; return HttpResponse.json({}, { status: 500 }) }),
    http.get('*/api/servers/alpha/compose', () => HttpResponse.json({ yaml_content: compose, version: compose })))
})
afterEach(() => { client.clear(); feed.close(); server.resetHandlers(); vi.useRealTimers(); vi.restoreAllMocks() })
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
async function drained(session = 'owner') { await waitFor(() => expect(client.getQueryData(queryKeys.operations.checkpoint(session))).toEqual({ cursor: feed.cursor, active_count: 1 })) }
function showObserver() { return render(<TestProviders client={client}><OperationObserver sessionId="owner" /></TestProviders>) }

it.each(['succeeded', 'failed', 'interrupted', 'cancelled', 'skipped'])('refreshes off-page %s outcomes directly from events without HTTP polling', async state => {
  render(<Shell />)
  await screen.findByText('配置：old'); await drained()
  fireEvent.click(screen.getByText('离开编辑器'))
  await screen.findByText('另一页面')
  compose = 'new'; feed.publish({ ...operation('one', state), data_changed: state !== 'succeeded' })
  await drained()
  expect(client.getQueryState(queryKeys.compose.detail('alpha'))?.isInvalidated).toBe(true)
  fireEvent.click(screen.getByText('返回编辑器'))
  await screen.findByText('配置：new')
  expect(pollingReads).toBe(0)
})

it('drains missed pages after reconnect from the last processed cursor', async () => {
  const view = render(<Shell />)
  await screen.findByText('配置：old'); await drained()
  view.unmount()
  await waitFor(() => expect(feed.activeConnections).toBe(0))
  feed.publish(...Array.from({ length: 400 }, (_, i) => ({ ...operation(`other-${i}`, 'succeeded'), kind: 'other' })), operation('old-operation', 'failed'))
  compose = 'reconnected'
  render(<Shell />)
  await drained()
  await screen.findByText('配置：reconnected')
  expect(feed.requests.at(-1)).toBe('1:0')
  expect(pollingReads).toBe(0)
})

it('isolates remounted sessions and rejects late invalidation after logout', async () => {
  const view = render(<Shell />)
  await screen.findByText('配置：old'); await drained()
  const held = deferred<void>()
  const entered = deferred<void>()
  const cancel = client.cancelQueries.bind(client)
  vi.spyOn(client, 'cancelQueries').mockImplementation(async filters => { entered.resolve(); await held.promise; return cancel(filters) })
  feed.publish(operation('late', 'failed'))
  await entered.promise
  view.unmount(); client.clear()
  held.resolve()
  await act(async () => { await Promise.resolve() })
  expect(client.getQueryData(queryKeys.operations.checkpoint('owner'))).toBeUndefined()
  vi.restoreAllMocks()
  compose = 'another-session'
  render(<Shell session="another-owner" />)
  await drained('another-owner')
  await screen.findByText('配置：another-session')
  expect(feed.requests.at(-1)).toBeNull()
})

it('keeps the processed page when disconnect interrupts the next page', async () => {
  const view = showObserver(); await drained()
  const held = deferred<void>(), entered = deferred<void>()
  const cancel = client.cancelQueries.bind(client)
  vi.spyOn(client, 'cancelQueries').mockImplementation(async filters => {
    if (JSON.stringify(filters?.queryKey).includes('beta')) { entered.resolve(); await held.promise }
    return cancel(filters)
  })
  feed.publish(...Array.from({ length: 200 }, (_, i) => operation(`alpha-${i}`, 'succeeded')),
    { ...operation('beta', 'succeeded'), resources: [{ kind: 'server', server_id: 'beta', generation: 1, path: '' }] })
  await entered.promise
  expect(client.getQueryData(queryKeys.operations.checkpoint('owner'))).toEqual({ cursor: '1:200', active_count: 1 })
  view.unmount()
  await waitFor(() => expect(feed.activeConnections).toBe(0))
  held.resolve(); vi.restoreAllMocks()
  const invalidate = vi.spyOn(client, 'invalidateQueries')
  showObserver(); await drained()
  expect(feed.requests.at(-1)).toBe('1:200')
  expect(invalidate.mock.calls.some(([filter]) => JSON.stringify(filter?.queryKey) === JSON.stringify(queryKeys.compose.detail('alpha')))).toBe(false)
  expect(invalidate.mock.calls.some(([filter]) => JSON.stringify(filter?.queryKey) === JSON.stringify(queryKeys.compose.detail('beta')))).toBe(true)
})

it('deduplicates acknowledged changes across StrictMode replay and remount', async () => {
  const view = render(<StrictMode><Shell /></StrictMode>)
  await screen.findByText('配置：old'); await drained()
  const invalidate = vi.spyOn(client, 'invalidateQueries')
  feed.publish(operation('one', 'succeeded')); await drained()
  view.unmount()
  render(<StrictMode><Shell /></StrictMode>)
  await drained()
  expect(invalidate.mock.calls.filter(([filters]) => JSON.stringify(filters?.queryKey) === JSON.stringify(queryKeys.compose.detail('alpha')))).toHaveLength(1)
})

it('resets business caches after restart and retains changes committed during reset refresh', async () => {
  render(<Shell />)
  await screen.findByText('配置：old'); await drained()
  const previousMapToken = client.getQueryData(queryKeys.map.resetRevision())
  let refreshed = false
  server.use(http.get('*/api/servers/alpha/compose', () => {
    if (!refreshed) { refreshed = true; feed.publish(operation('during-reset', 'failed')) }
    return HttpResponse.json({ yaml_content: compose, version: compose })
  }))
  compose = 'resynchronized'; feed.restart()
  await drained()
  await screen.findByText('配置：resynchronized')
  expect(client.getQueryData(queryKeys.map.resetRevision())).not.toBe(previousMapToken)
  expect(client.getQueryData(queryKeys.operations.checkpoint('owner'))).toEqual({ cursor: '2:1', active_count: 1 })
})

it.each(['reset', 'terminal'])('replaces a pending initial business read during %s synchronization', async mode => {
  const captured = deferred<void>(), release = deferred<void>()
  let first = true
  if (mode === 'terminal') client.setQueryData(queryKeys.operations.checkpoint('owner'), { cursor: '1:0', active_count: 1 })
  server.use(http.get('*/api/servers/alpha/compose', async () => {
    const content = compose
    if (first) { first = false; captured.resolve(); await release.promise }
    return HttpResponse.json({ yaml_content: content, version: content })
  }))
  const view = render(<TestProviders client={client}><Editor /></TestProviders>)
  await captured.promise
  compose = 'new'
  if (mode === 'terminal') feed.publish(operation('completed', 'succeeded'))
  showObserver()
  await drained()
  await screen.findByText('配置：new')
  await act(async () => { release.resolve() })
  expect(client.getQueryData(queryKeys.compose.detail('alpha'))).toMatchObject({ yaml_content: 'new' })
  view.unmount()
})

it.each(['world_restore', 'chunk_prune_apply', 'snapshot_restore', 'file_upload', 'archive_extract'])('refreshes scoped file and world data after %s partially fails', async kind => {
  showObserver(); await drained()
  const fileKey = queryKeys.files.list('alpha', '/data'), mapKey = queryKeys.map.regions('alpha', 'world/region'), otherKey = queryKeys.files.list('beta', '/data')
  for (const key of [fileKey, mapKey, otherKey]) client.setQueryData(key, [])
  feed.publish({ ...operation('file-world', 'failed'), kind, data_changed: true }); await drained()
  expect(client.getQueryState(fileKey)?.isInvalidated).toBe(true)
  expect(client.getQueryState(mapKey)?.isInvalidated).toBe(true)
  expect(client.getQueryState(otherKey)?.isInvalidated).toBe(false)
})

it('refreshes global file roots while preserving unrelated archive and read-only map caches', async () => {
  showObserver(); await drained()
  const alpha = queryKeys.files.list('alpha', '/data'), beta = queryKeys.files.list('beta', '/data'), map = queryKeys.map.regions('beta', 'world/region')
  for (const key of [alpha, beta, map]) client.setQueryData(key, [])
  feed.publish({ ...operation('global', 'failed'), kind: 'snapshot_restore', data_changed: true, resources: [{ kind: 'files', server_id: null, generation: null, path: '' }] }); await drained()
  for (const key of [alpha, beta, map]) expect(client.getQueryState(key)?.isInvalidated).toBe(true)
  for (const key of [alpha, beta, map]) client.setQueryData(key, [])
  feed.publish({ ...operation('archive', 'succeeded'), kind: 'archive_publish', resources: [{ kind: 'archive', server_id: null, generation: null, path: 'upload.zip' }] },
    { ...operation('tile', 'succeeded'), kind: 'map_render', data_changed: true }); await drained()
  for (const key of [alpha, beta, map]) expect(client.getQueryState(key)?.isInvalidated).toBe(false)
})

it.each([
  ['server_create', queryKeys.serverInfos.all], ['server_sync', queryKeys.serverStatuses.all],
  ['self_check', queryKeys.selfCheck.all], ['dns_update', queryKeys.dns.all],
  ['archive_publish', queryKeys.archive.all], ['archive_delete', queryKeys.archive.all],
  ['map_initialize', queryKeys.map.status('alpha')], ['server_restart', queryKeys.cron.all],
] as const)('refreshes %s resources after streamed completion', async (kind, key) => {
  showObserver(); await drained()
  client.setQueryData(key, { retained: true })
  feed.publish({ ...operation('finished', 'succeeded'), kind }); await drained()
  expect(client.getQueryState(key)?.isInvalidated).toBe(true)
})

it('refreshes later effective changes of the same terminal operation', async () => {
  showObserver(); await drained()
  const key = queryKeys.files.list('alpha', '/data')
  feed.publish({ ...operation('same', 'failed'), kind: 'file_write', data_changed: true }); await drained()
  client.setQueryData(key, [])
  feed.publish({ ...operation('same', 'failed'), kind: 'file_write', data_changed: true, updated_at: '2026-09-29T00:00:00Z' }); await drained()
  expect(client.getQueryState(key)?.isInvalidated).toBe(true)
})
