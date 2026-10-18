import { act, fireEvent, render, renderHook, screen, waitFor } from '@testing-library/react'
import { afterAll, afterEach, beforeAll, beforeEach, expect, it, vi } from 'vitest'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { createTestClient, deferred } from '@/test/http'
import { createTaskEvents, taskEvent, taskResponse } from '@/test/taskEvents'
import { TestProviders } from '@/test/TestProviders'
import { useChunkPruneController } from './useChunkPruneController'

vi.mock('@/features/world/useWorldMapController', () => ({
  setWorldMapMode: vi.fn(),
  useWorldMapController: () => ({ server: { serverStopped: true }, map: { regionRelpath: 'world/region', rawMode: 'regions' }, claims: {}, players: {} }),
}))
const server = setupServer()
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterAll(() => server.close())
let client: ReturnType<typeof createTestClient>
let feed: ReturnType<typeof createTaskEvents>
beforeEach(() => {
  client = createTestClient(); feed = createTaskEvents()
  server.use(feed.handler,
    http.get('*/api/servers/:id/chunk-prune/settings', () => HttpResponse.json({ default_threshold_seconds: 30 })),
    http.get('*/api/servers/:id/chunk-prune/previews/:task/geometry', () => HttpResponse.json({ dimensions: [] })),
  )
})
afterEach(() => { client.clear(); feed.close(); server.resetHandlers() })
const wrapper = ({ children }: { children: React.ReactNode }) => <TestProviders client={client}>{children}</TestProviders>

function ready(taskId = 'preview', availability = 'ready') {
  return {
    server_id: 'alpha', preview: { task_id: taskId, input_version: 'inputs', expires_at: null, availability, apply_task_id: null },
    preview_task: taskEvent(taskResponse(taskId, { task_type: 'chunk_prune_preview', status: 'completed', result: { mode: 'regions', dry_run: true, threshold_seconds: 30 } })), apply_task: null,
  }
}

it.each([false, true])('keeps server identities isolated when acceptance is delayed: %s', async delayed => {
  const release = deferred<void>()
  const requests: string[] = []
  let cancels = 0
  server.use(
    http.post('*/api/servers/:id/chunk-prune/preview', async ({ params }) => {
      const serverId = String(params.id)
      requests.push(serverId)
      if (serverId === 'alpha' && delayed) await release.promise
      const task = taskResponse(`${serverId}-accepted`, { task_type: 'chunk_prune_preview', server_id: serverId })
      feed.upsert(task)
      return HttpResponse.json({ task_id: task.task_id }, { status: 202 })
    }),
    http.post('*/api/tasks/:id/cancel', () => { cancels++; return HttpResponse.json({}) }),
  )
  const view = renderHook(({ serverId }) => useChunkPruneController(serverId), { wrapper, initialProps: { serverId: 'alpha' } })
  await waitFor(() => expect(view.result.current.canPreview).toBe(true))
  let alphaRequest!: Promise<void>
  act(() => { alphaRequest = view.result.current.startPreview() })
  await waitFor(() => expect(requests).toEqual(['alpha']))
  if (!delayed) {
    await act(async () => { await alphaRequest })
    await waitFor(() => expect(view.result.current.previewTaskId).toBe('alpha-accepted'))
  }
  view.rerender({ serverId: 'beta' })
  await waitFor(() => expect(view.result.current.canPreview).toBe(true))
  expect(view.result.current.previewStarting).toBe(false)
  expect(view.result.current.previewTaskId).toBeNull()
  await act(async () => { await view.result.current.startPreview() })
  await waitFor(() => expect(view.result.current.previewTaskId).toBe('beta-accepted'))
  await act(async () => { release.resolve(); await alphaRequest })
  expect(view.result.current.previewTaskId).toBe('beta-accepted')
  expect(view.result.current.previewTask?.serverId).toBe('beta')
  expect(view.result.current.previewActive).toBe(true)
  expect(requests).toEqual(['alpha', 'beta'])
  expect(cancels).toBe(0)
})

function Controls({ serverId = 'alpha' }: { serverId?: string }) {
  const state = useChunkPruneController(serverId)
  return <><button disabled={!state.canApply} onClick={state.startApply}>提交删除</button><output>{state.previewTaskId}</output><span>{state.applyError}</span>{state.confirmDialog}</>
}

it.each(['disconnect', 'preview', 'server'] as const)('rechecks %s before executing an already-open confirmation', async change => {
  feed.pruneStates([ready()])
  let applies = 0
  server.use(http.post('*/api/servers/:id/chunk-prune/apply', () => { applies++; return HttpResponse.json({ task_id: 'apply' }, { status: 202 }) }))
  const view = render(<Controls />, { wrapper })
  await waitFor(() => expect((screen.getByText('提交删除') as HTMLButtonElement).disabled).toBe(false))
  fireEvent.click(screen.getByText('提交删除'))
  const confirmation = await screen.findByRole('button', { name: '删除区块' })
  if (change === 'disconnect') {
    act(() => feed.close())
    await waitFor(() => expect((screen.getByText('提交删除') as HTMLButtonElement).disabled).toBe(true))
  } else if (change === 'preview') {
    act(() => feed.pruneStates([ready('replacement')]))
    await screen.findByText('replacement')
  } else {
    view.rerender(<Controls serverId="beta" />)
    await waitFor(() => expect(screen.getByRole('status', { hidden: true }).textContent).toBe(''))
  }
  fireEvent.click(confirmation)
  await waitFor(() => expect(screen.queryByRole('alertdialog')).toBeNull())
  expect(applies).toBe(0)
})

it('preserves backend expiry validation for a connected confirmation of the same preview', async () => {
  feed.pruneStates([ready()])
  let applies = 0
  server.use(http.post('*/api/servers/alpha/chunk-prune/apply', () => {
    applies++
    return HttpResponse.json({ detail: { code: 'prune_preview_expired', message: '预览已过期，请重新生成预览' } }, { status: 409 })
  }))
  render(<Controls />, { wrapper })
  await waitFor(() => expect((screen.getByText('提交删除') as HTMLButtonElement).disabled).toBe(false))
  fireEvent.click(screen.getByText('提交删除'))
  act(() => feed.pruneStates([ready('preview', 'expired')]))
  await waitFor(() => expect((screen.getByText('提交删除') as HTMLButtonElement).disabled).toBe(true))
  fireEvent.click(screen.getByRole('button', { name: '删除区块' }))
  await screen.findByText('预览已过期，请重新生成预览')
  expect(applies).toBe(1)
})
