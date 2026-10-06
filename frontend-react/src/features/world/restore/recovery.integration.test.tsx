import { act, renderHook, waitFor } from '@testing-library/react'
import { afterAll, afterEach, beforeAll, beforeEach, expect, it, vi } from 'vitest'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { createTestClient } from '@/test/http'
import { TestProviders } from '@/test/TestProviders'
import { readEventStream } from '@/shared/http/eventStream'
import type { ApiError } from '@/shared/http/api'
import { useSnapshotOperation } from '@/features/backups/commands'
import { useSnapshotPreview } from '@/features/backups/commands'
import type { RestorationSelection } from '@/features/backups/contracts'
import type { SnapshotPreviewRequest } from '@/features/backups/contracts'

const server = setupServer()
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterAll(() => server.close())
let client: ReturnType<typeof createTestClient>
beforeEach(() => { client = createTestClient() })
afterEach(() => { client.clear(); server.resetHandlers(); vi.restoreAllMocks() })
const wrapper = ({ children }: { children: React.ReactNode }) => <TestProviders client={client}>{children}</TestProviders>

it('latches world selection and leaves the accepted task running when its observer unmounts', async () => {
  const bodies: unknown[] = []
  let cancellations = 0
  server.use(
    http.get('*/api/snapshots/restorations/active', () => HttpResponse.json({ total: 0, restorations: [] })),
    http.post('*/api/snapshots/restorations', async ({ request }) => {
      bodies.push(await request.json())
      return HttpResponse.json({ task_id: 'restore', skipped_paths: [] }, { status: 202 })
    }),
    http.get('*/api/tasks/restore', () => HttpResponse.json({ task_id: 'restore', status: 'running', message: '正在创建安全快照' })),
    http.post('*/api/tasks/restore/cancel', () => { cancellations++; return HttpResponse.json({}) }),
  )
  const selection: RestorationSelection = { type: 'regions', region_dir_relpath: 'world/region', regions: [[0, 0]] }
  const view = renderHook(() => useSnapshotOperation({ kind: 'world', server_id: 'alpha', selection }), { wrapper })
  await waitFor(() => expect(view.result.current.busy).toBe(false))
  await act(async () => { await view.result.current.start('snapshot') })
  await waitFor(() => expect(view.result.current.state.message).toBe('正在创建安全快照'))
  selection.regions = [[9, 9]]
  view.rerender()
  expect(bodies).toEqual([{ source_snapshot_id: 'snapshot', entry_point: 'world', scope: { kind: 'world', server_id: 'alpha', selection: { type: 'regions', region_dir_relpath: 'world/region', regions: [[0, 0]] } } }])
  expect(view.result.current.state.active).toBe(true)
  view.unmount()
  expect(cancellations).toBe(0)
})

it.each([401, 403, 409, 422, 500])('preserves structured HTTP %s errors from the finite transport', async status => {
  server.use(http.post('*/api/stream-test', () => HttpResponse.json({ detail: { code: 'restoration_identity_conflict', message: '目标服务器实例不匹配' } }, { status })))
  let received: ApiError | undefined
  await readEventStream({ url: '/stream-test', onEvent: () => { throw new Error('unexpected event') }, onError: (_, error) => { received = error } })
  expect(received?.status).toBe(status)
  expect(received?.message).toBe('目标服务器实例不匹配')
  expect(received?.detail).toEqual({ code: 'restoration_identity_conflict', message: '目标服务器实例不匹配' })
})

it('ends a ready preview session when its owner unmounts and shows heartbeat expiry', async () => {
  let heartbeat: (() => void) | undefined
  const nativeInterval = globalThis.setInterval.bind(globalThis)
  vi.spyOn(window, 'setInterval').mockImplementation((callback, timeout) => {
    if (timeout === 30_000) heartbeat = callback
    return nativeInterval(callback, timeout)
  })
  const ended: string[] = []
  server.use(
    http.post('*/api/snapshots/previews', () => HttpResponse.json({ task_id: 'prepare' }, { status: 202 })),
    http.get('*/api/tasks/prepare', () => HttpResponse.json({ task_id: 'prepare', task_type: 'snapshot_preview', status: 'completed', result: { preview_id: 'session', kind: 'map' } })),
    http.post('*/api/snapshots/previews/session/heartbeat', () => HttpResponse.json({ detail: '预览会话已过期' }, { status: 404 })),
    http.delete('*/api/snapshots/previews/:session', ({ params }) => { ended.push(String(params.session)); return HttpResponse.json({ task_id: 'cleanup' }, { status: 202 }) }),
    http.get('*/api/tasks/cleanup', () => HttpResponse.json({ task_id: 'cleanup', status: 'completed', result: {} })),
  )
  const request: SnapshotPreviewRequest = { source_snapshot_id: 'snapshot', scope: { kind: 'world', server_id: 'alpha', selection: { type: 'regions', region_dir_relpath: 'world/region', regions: [[0, 0]] } } }
  const view = renderHook(() => useSnapshotPreview(request), { wrapper })
  await waitFor(() => expect(view.result.current.result?.preview_id).toBe('session'))
  act(() => heartbeat?.())
  await waitFor(() => expect(view.result.current.error).toContain('重新生成'))
  expect(view.result.current.result).toBeNull()
  view.unmount()
  await waitFor(() => expect(ended).toEqual(['session']))
})
