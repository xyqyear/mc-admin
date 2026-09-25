import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterAll, afterEach, beforeAll, beforeEach, expect, it, vi } from 'vitest'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { onlineManager, useQuery } from '@tanstack/react-query'
import { Link, Route, Routes } from 'react-router'
import { StrictMode } from 'react'
import { queryKeys } from '@/shared/http/api'
import { createTestClient } from '@/test/http'
import { TestProviders } from '@/test/TestProviders'
import { composeOptions } from '@/features/configuration/queries'
import { OperationObserver } from '@/app/operations/OperationObserver'
import type { Operation } from '@/shared/operations/contracts'

const server = setupServer()
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterAll(() => server.close())
let client: ReturnType<typeof createTestClient>
let operations: Operation[]
let compose: string
let reads: number
const operation = (id: string, state = 'running'): Operation => ({ operation_id: id, kind: 'server_rebuild', state, legacy_id: id, failure_code: null, data_changed: false, resources: [{ kind: 'server', server_id: 'alpha', generation: 1, path: '' }] })
beforeEach(() => {
  client = createTestClient(); operations = [operation('one')]; compose = 'old'; reads = 0
  server.use(
    http.get('*/api/operations', ({ request }) => {
      const offset = Number(new URL(request.url).searchParams.get('offset'))
      return HttpResponse.json(operations.slice(offset, offset + 1000))
    }),
    http.get('*/api/servers/alpha/compose', () => { reads++; return HttpResponse.json({ yaml_content: compose, version: compose }) }),
  )
})
afterEach(() => { client.clear(); server.resetHandlers(); onlineManager.setOnline(true); vi.restoreAllMocks() })
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
async function poll() { await act(async () => { await client.refetchQueries({ queryKey: queryKeys.operations.all }) }) }

it.each(['succeeded', 'failed', 'interrupted', 'cancelled'])('refreshes after leaving the submitting page when an operation becomes %s and deduplicates completion', async state => {
  render(<Shell />)
  await screen.findByText('配置：old')
  fireEvent.click(screen.getByText('离开编辑器'))
  await screen.findByText('另一页面')
  const invalidate = vi.spyOn(client, 'invalidateQueries')
  compose = 'new'; operations = [{ ...operation('one', state), data_changed: state !== 'succeeded' }]
  await poll()
  await waitFor(() => expect(client.getQueryState(queryKeys.compose.detail('alpha'))?.isInvalidated).toBe(true))
  const count = invalidate.mock.calls.length
  await poll()
  expect(invalidate).toHaveBeenCalledTimes(count)
  fireEvent.click(screen.getByText('返回编辑器'))
  await screen.findByText('配置：new')
  expect(reads).toBe(2)
})

it('discovers missed terminal operations after reconnect, including the next history page', async () => {
  render(<Shell />)
  await screen.findByText('配置：old')
  onlineManager.setOnline(false)
  operations = [...Array.from({ length: 1000 }, (_, i) => ({ ...operation(`other-${i}`, 'succeeded'), kind: 'other' })), operation('one', 'failed')]
  compose = 'reconnected'
  await act(async () => { onlineManager.setOnline(true) })
  await screen.findByText('配置：reconnected')
  expect(client.getQueryData<Operation[]>(queryKeys.operations.session('owner'))).toHaveLength(1001)
})

it('clears the observer session at logout and discovers completion for the next login', async () => {
  operations = [operation('one', 'succeeded')]
  const view = render(<Shell />)
  await screen.findByText('配置：old')
  await poll()
  view.unmount()
  client.clear()
  expect(client.getQueryCache().getAll()).toHaveLength(0)
  compose = 'new-session'
  render(<Shell session="another-owner" />)
  await screen.findByText('配置：new-session')
  await waitFor(() => expect(client.getQueryData(queryKeys.operations.session('another-owner'))).toBeDefined())
  expect(client.getQueryData(queryKeys.operations.session('owner'))).toBeUndefined()
})

it('does not turn a polling failure into completion and resumes after the API recovers', async () => {
  render(<Shell />)
  await screen.findByText('配置：old')
  server.use(http.get('*/api/operations', () => HttpResponse.json({ detail: '暂时不可用' }, { status: 503 })))
  await poll()
  expect(reads).toBe(1)
  server.resetHandlers()
  operations = [operation('one', 'succeeded')]; compose = 'recovered'
  server.use(http.get('*/api/operations', () => HttpResponse.json(operations)), http.get('*/api/servers/alpha/compose', () => HttpResponse.json({ yaml_content: compose, version: compose })))
  await poll()
  await screen.findByText('配置：recovered')
})

it('polls an active operation through completion without a page callback', async () => {
  render(<Shell />)
  await screen.findByText('配置：old')
  compose = 'polled'; operations = [operation('one', 'succeeded')]
  await screen.findByText('配置：polled', {}, { timeout: 4000 })
})

it('keeps following an active operation outside the newest history page', async () => {
  operations = [...Array.from({ length: 1000 }, (_, i) => ({ ...operation(`other-${i}`, 'succeeded'), kind: 'other' })), operation('old-active')]
  server.use(http.get('*/api/operations/old-active', () => HttpResponse.json(operation('old-active', 'succeeded'))))
  render(<Shell />)
  await screen.findByText('配置：old')
  await waitFor(() => expect(client.getQueryData<Operation[]>(queryKeys.operations.session('owner'))).toHaveLength(1001))
  compose = 'older completed'
  await poll()
  await screen.findByText('配置：older completed')
})

it('deduplicates cached completion during StrictMode effect replay', async () => {
  operations = [operation('one', 'succeeded')]
  client.setQueryData(queryKeys.operations.session('owner'), operations)
  const invalidate = vi.spyOn(client, 'invalidateQueries')
  render(<StrictMode><Shell /></StrictMode>)
  await screen.findByText('配置：old')
  await poll()
  expect(invalidate.mock.calls.filter(([filters]) => JSON.stringify(filters?.queryKey) === JSON.stringify(queryKeys.compose.detail('alpha')))).toHaveLength(1)
})

it('resynchronizes a missing old operation once after reconnect without dropping newly discovered records', async () => {
  let missingReads = 0
  server.use(http.get('*/api/operations/one', () => { missingReads++; return HttpResponse.json({ detail: '操作不存在' }, { status: 404 }) }))
  render(<Shell />)
  await screen.findByText('配置：old')
  await waitFor(() => expect(client.getQueryData<Operation[]>(queryKeys.operations.session('owner'))).toHaveLength(1))
  onlineManager.setOnline(false)
  operations = [{ ...operation('newly-discovered', 'succeeded'), kind: 'other' }]
  compose = 'after retention'
  await act(async () => { onlineManager.setOnline(true) })
  await screen.findByText('配置：after retention')
  expect(client.getQueryState(queryKeys.operations.session('owner'))?.status).toBe('success')
  expect(client.getQueryData<Operation[]>(queryKeys.operations.session('owner'))?.some(record => record.operation_id === 'newly-discovered')).toBe(true)
  await poll()
  expect(missingReads).toBe(1)
  expect(client.getQueryData<Operation[]>(queryKeys.operations.session('owner'))?.some(record => record.operation_id === 'one')).toBe(false)
  operations = [operation('next', 'succeeded')]; compose = 'next completion'
  await poll()
  await screen.findByText('配置：next completion')
})

it.each(['world_restore', 'chunk_prune_apply', 'snapshot_restore', 'file_upload', 'archive_extract'])('refreshes file and world resources after %s partially changes data on another page', async kind => {
  const fileKey = queryKeys.files.list('alpha', '/data')
  const mapKey = queryKeys.map.regions('alpha', 'world/region')
  const otherKey = queryKeys.files.list('beta', '/data')
  client.setQueryData(fileKey, { items: [] })
  client.setQueryData(mapKey, [[0, 0, 1]])
  client.setQueryData(otherKey, { items: [] })
  operations = [{ ...operation('file-world'), kind }]
  const view = render(<TestProviders client={client}><OperationObserver sessionId="owner" /><div>任务页面已关闭</div></TestProviders>)
  await waitFor(() => expect(client.getQueryData(queryKeys.operations.session('owner'))).toBeDefined())
  operations = [{ ...operation('file-world', 'failed'), kind, data_changed: true }]
  await poll()
  await waitFor(() => expect(client.getQueryState(fileKey)?.isInvalidated).toBe(true))
  expect(client.getQueryState(mapKey)?.isInvalidated).toBe(true)
  expect(client.getQueryState(otherKey)?.isInvalidated).toBe(false)
  const invalidate = vi.spyOn(client, 'invalidateQueries')
  await poll()
  expect(invalidate).not.toHaveBeenCalled()
  view.unmount()
})

it('refreshes all server files for a global file-root operation without treating archive-root resources as servers', async () => {
  const alpha = queryKeys.files.list('alpha', '/data')
  const beta = queryKeys.files.list('beta', '/data')
  const map = queryKeys.map.regions('beta', 'world/region')
  for (const key of [alpha, beta, map]) client.setQueryData(key, [])
  operations = [{ ...operation('global', 'failed'), kind: 'snapshot_restore', data_changed: true, resources: [{ kind: 'files', server_id: null, generation: null, path: '' }] }]
  render(<TestProviders client={client}><OperationObserver sessionId="owner" /></TestProviders>)
  await waitFor(() => expect(client.getQueryState(beta)?.isInvalidated).toBe(true))
  expect(client.getQueryState(alpha)?.isInvalidated).toBe(true)
  expect(client.getQueryState(map)?.isInvalidated).toBe(true)
  for (const key of [alpha, beta, map]) client.setQueryData(key, [])
  operations = [{ ...operation('archive', 'succeeded'), kind: 'archive_publish', resources: [{ kind: 'archive', server_id: null, generation: null, path: 'upload.zip' }] }]
  await poll()
  for (const key of [alpha, beta, map]) expect(client.getQueryState(key)?.isInvalidated).toBe(false)
})

it('refreshes map initialization across pages without refreshing after tile renders', async () => {
  const status = queryKeys.map.status('alpha')
  const regions = queryKeys.map.regions('alpha', 'world/region')
  const unrelated = queryKeys.map.status('beta')
  for (const key of [status, regions, unrelated]) client.setQueryData(key, [])
  operations = [{ ...operation('initialize', 'failed'), kind: 'map_initialize', data_changed: true }]
  render(<TestProviders client={client}><OperationObserver sessionId="owner" /></TestProviders>)
  await waitFor(() => expect(client.getQueryState(status)?.isInvalidated).toBe(true))
  expect(client.getQueryState(regions)?.isInvalidated).toBe(true)
  expect(client.getQueryState(unrelated)?.isInvalidated).toBe(false)
  for (const key of [status, regions]) client.setQueryData(key, [])
  operations = [{ ...operation('tile', 'succeeded'), kind: 'map_render', data_changed: true }]
  await poll()
  expect(client.getQueryState(status)?.isInvalidated).toBe(false)
  expect(client.getQueryState(regions)?.isInvalidated).toBe(false)
})
