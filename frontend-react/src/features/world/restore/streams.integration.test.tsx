import { act, renderHook, waitFor } from '@testing-library/react'
import { afterAll, afterEach, beforeAll, beforeEach, expect, it, vi } from 'vitest'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { createTestClient } from '@/test/http'
import { TestProviders } from '@/test/TestProviders'
import { readEventStream } from '@/shared/http/eventStream'
import type { ApiError } from '@/shared/http/api'
import { useSnapshotOperation } from '@/features/backups/commands'
import { useRestorePreview } from '@/features/world/restore/useRestorePreview'
import type { RestorationSelection } from '@/features/backups/contracts'
import type { RestorePreviewRequest } from '@/features/world/restore/contracts'

const server = setupServer()
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterAll(() => server.close())
let client: ReturnType<typeof createTestClient>
beforeEach(() => { client = createTestClient() })
afterEach(() => { client.clear(); server.resetHandlers(); vi.restoreAllMocks() })
const wrapper = ({ children }: { children: React.ReactNode }) => <TestProviders client={client}>{children}</TestProviders>
const encoder = new TextEncoder()
const event = (data: object) => encoder.encode(`data: ${JSON.stringify(data)}\n\n`)

it('latches world selection and leaves the accepted task running when its observer unmounts', async () => {
  const bodies: unknown[] = []
  let cancellations = 0
  server.use(
    http.get('*/api/snapshots/restorations', () => HttpResponse.json({ total: 0, restorations: [] })),
    http.post('*/api/snapshots/restorations', async ({ request }) => {
      bodies.push(await request.json())
      return HttpResponse.json({ task_id: 'restore', skipped_paths: [] }, { status: 202 })
    }),
    http.get('*/api/tasks/restore', () => HttpResponse.json({ task_id: 'restore', status: 'running', message: '正在创建安全快照' })),
    http.post('*/api/tasks/restore/cancel', () => { cancellations++; return HttpResponse.json({}) }),
  )
  const selection: RestorationSelection = { type: 'regions', region_dir_relpath: 'world/region', regions: [[0, 0]] }
  const view = renderHook(() => useSnapshotOperation({ kind: 'world', server_id: 'alpha', selection }), { wrapper })
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
  const nativeInterval = window.setInterval.bind(window)
  vi.spyOn(window, 'setInterval').mockImplementation((callback: TimerHandler, timeout?: number, ...args: unknown[]) => {
    if (timeout === 30_000) { heartbeat = callback as () => void; return 987654 }
    return nativeInterval(callback, timeout, ...args)
  })
  const ended: string[] = []
  server.use(
    http.post('*/api/servers/alpha/world-restore/preview', () => new HttpResponse(event({ event_type: 'ready', session_id: 'session' }))),
    http.post('*/api/servers/alpha/world-restore/preview/session/heartbeat', () => HttpResponse.json({ detail: '预览会话已过期' }, { status: 404 })),
    http.delete('*/api/servers/alpha/world-restore/preview/:session', ({ params }) => { ended.push(String(params.session)); return HttpResponse.json({}) }),
  )
  const request: RestorePreviewRequest = { sourceSnapshotId: 'snapshot', selection: { type: 'regions', region_dir_relpath: 'world/region', regions: [[0, 0]] } }
  const view = renderHook(() => useRestorePreview('alpha', request), { wrapper })
  await waitFor(() => expect(view.result.current.ready).toBe(true))
  act(() => heartbeat?.())
  await waitFor(() => expect(view.result.current.error).toContain('重新生成预览'))
  expect(view.result.current.ready).toBe(false)
  view.unmount()
  await waitFor(() => expect(ended).toEqual(['session']))
})
