import { act, renderHook, waitFor } from '@testing-library/react'
import { afterAll, afterEach, beforeAll, beforeEach, expect, it } from 'vitest'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { createTestClient, deferred } from '@/test/http'
import { createTaskEvents, taskEvent, taskResponse } from '@/test/taskEvents'
import { TestProviders } from '@/test/TestProviders'
import { useActiveRestorations } from '@/features/backups/queries'
import { useChunkPruneState } from './queries'

const server = setupServer()
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterAll(() => server.close())
let client: ReturnType<typeof createTestClient>
let feed: ReturnType<typeof createTaskEvents>
let stateReads: number
let detailReads: number
beforeEach(() => {
  client = createTestClient(); feed = createTaskEvents(); stateReads = 0; detailReads = 0
  server.use(feed.handler,
    http.get('*/api/servers/*/chunk-prune/state', () => { stateReads++; return HttpResponse.json({}, { status: 500 }) }),
    http.get('*/api/tasks/:id', () => { detailReads++; return HttpResponse.json({}, { status: 503 }) }))
})
afterEach(() => { client.clear(); feed.close(); server.resetHandlers() })
const wrapper = ({ children }: { children: React.ReactNode }) => <TestProviders client={client}>{children}</TestProviders>
const result = { mode: 'regions', dry_run: true, region_dirs: 1, regions_scanned: 2, chunks_scanned: 20, chunks_selected: 10, regions_selected: 1 }
const preview = (availability = 'ready') => ({ task_id: 'preview', input_version: 'inputs', expires_at: '2099-10-18T00:00:00Z', availability, apply_task_id: null })
const record = (status: 'running' | 'completed' = 'completed') => ({
  server_id: 'alpha', preview: preview(),
  preview_task: taskEvent(taskResponse('preview', { task_type: 'chunk_prune_preview', status, progress: 100,
    progress_details: { kind: 'regions', regions_processed: 2, regions_total: 2 }, result })),
  apply_task: null,
})

it('shares discovery with recovery and confirms an empty state without polling', async () => {
  const view = renderHook(() => ({ prune: useChunkPruneState('alpha'), restoration: useActiveRestorations('alpha') }), { wrapper })
  expect(view.result.current.prune.checking).toBe(true)
  await waitFor(() => expect(view.result.current.prune.checking).toBe(false))
  expect(view.result.current.restoration.checking).toBe(false)
  expect(view.result.current.prune.data).toEqual({ preview: null, previewTask: null, applyTask: null })
  expect(feed.connections).toBe(1)
  expect(stateReads).toBe(0)
})

it('retains dismissed preview results and observes expiry or consumption without state reads', async () => {
  feed.pruneStates([record()])
  const first = renderHook(() => useChunkPruneState('alpha'), { wrapper })
  await waitFor(() => expect(first.result.current.data?.previewTask?.result).toEqual(result))
  expect(first.result.current.data?.previewTask?.progressDetails).toEqual({ kind: 'regions', regions_processed: 2, regions_total: 2 })
  act(() => feed.remove('preview'))
  const second = renderHook(() => useChunkPruneState('alpha'), { wrapper })
  await waitFor(() => expect(second.result.current.data?.preview?.availability).toBe('ready'))
  expect(second.result.current.data?.previewTask?.status).toBe('completed')
  act(() => feed.pruneStates([{ ...record(), preview: preview('expired') }]))
  await waitFor(() => expect(second.result.current.data?.preview?.availability).toBe('expired'))
  act(() => feed.pruneStates([{ ...record(), preview: { ...preview('consumed'), apply_task_id: 'apply' } }]))
  await waitFor(() => expect(second.result.current.data?.preview?.apply_task_id).toBe('apply'))
  expect(detailReads).toBe(0)
  expect(stateReads).toBe(0)
  expect(feed.connections).toBe(1)
})

it('keeps running 100-percent progress and disconnect guarded until an authoritative result arrives', async () => {
  feed.pruneStates([record('running')])
  const view = renderHook(() => useChunkPruneState('alpha'), { wrapper })
  await waitFor(() => expect(view.result.current.data?.previewTask?.status).toBe('running'))
  expect(view.result.current.data?.previewTask?.result).toBeUndefined()
  act(() => feed.close())
  await waitFor(() => expect(view.result.current.checking).toBe(true))
  expect(view.result.current.data?.previewTask?.status).toBe('running')
  expect(stateReads).toBe(0)
  feed.pruneStates([record()])
  await waitFor(() => expect(view.result.current.data?.previewTask?.status).toBe('completed'), { timeout: 3000 })
  expect(view.result.current.data?.previewTask?.result).toEqual(result)
})

it('keeps excluded terminal results active until the one detail read succeeds', async () => {
  const release = deferred<void>()
  const task = record().preview_task
  feed.pruneStates([{ ...record(), preview_task: { ...task, result_included: false, result: null } }])
  server.use(http.get('*/api/tasks/preview', async () => { detailReads++; await release.promise; return HttpResponse.json(taskResponse('preview', { task_type: 'chunk_prune_preview', status: 'completed', result })) }))
  const view = renderHook(() => useChunkPruneState('alpha'), { wrapper })
  await waitFor(() => expect(detailReads).toBe(1))
  expect(view.result.current.data?.previewTask?.status).toBe('running')
  await act(async () => { release.resolve() })
  await waitFor(() => expect(view.result.current.data?.previewTask?.status).toBe('completed'))
  expect(view.result.current.data?.previewTask?.result).toEqual(result)
  expect(detailReads).toBe(1)
  expect(stateReads).toBe(0)
})

it('retains an accepted task before its domain index arrives and rejects invalid availability', async () => {
  feed.upsert(taskResponse('accepted', { task_type: 'chunk_prune_preview' }))
  const view = renderHook(() => useChunkPruneState('alpha', { preview: 'accepted' }), { wrapper })
  await waitFor(() => expect(view.result.current.data?.previewTask?.taskId).toBe('accepted'))
  expect(view.result.current.data?.previewTask?.status).toBe('running')
  expect(view.result.current.data?.preview).toBeNull()
  act(() => feed.pruneStates([{ ...record(), preview: preview('unexpected') }]))
  await waitFor(() => expect(view.result.current.checking).toBe(true))
  expect(view.result.current.data).toBeUndefined()
})
