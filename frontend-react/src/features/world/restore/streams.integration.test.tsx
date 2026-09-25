import { act, renderHook, waitFor } from '@testing-library/react'
import { afterAll, afterEach, beforeAll, beforeEach, expect, it, vi } from 'vitest'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { createTestClient } from '@/test/http'
import { TestProviders } from '@/test/TestProviders'
import { readEventStream } from '@/shared/http/eventStream'
import type { ApiError } from '@/shared/http/api'
import { useRestorationStream } from '@/features/world/restore/useRestorationStream'
import { useRestorePreview } from '@/features/world/restore/useRestorePreview'
import type { RestorationSelection, RestorePreviewRequest } from '@/features/world/restore/contracts'

const server = setupServer()
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterAll(() => server.close())
let client: ReturnType<typeof createTestClient>
beforeEach(() => { client = createTestClient() })
afterEach(() => { client.clear(); server.resetHandlers(); vi.restoreAllMocks() })
const wrapper = ({ children }: { children: React.ReactNode }) => <TestProviders client={client}>{children}</TestProviders>
const encoder = new TextEncoder()
const event = (data: object) => encoder.encode(`data: ${JSON.stringify(data)}\n\n`)

it('latches the selected restore request and aborts its finite stream when the page unmounts', async () => {
  const bodies: unknown[] = []
  let signal: AbortSignal | undefined
  let writer!: ReadableStreamDefaultController<Uint8Array>
  server.use(http.post('*/api/servers/alpha/world-restore/restore', async ({ request }) => {
    bodies.push(await request.json()); signal = request.signal
    return new HttpResponse(new ReadableStream<Uint8Array>({ start(controller) { writer = controller; controller.enqueue(event({ event_type: 'start', message: 'started' })) } }), { headers: { 'Content-Type': 'text/event-stream' } })
  }))
  const view = renderHook(() => useRestorationStream('alpha'), { wrapper })
  const selection: RestorationSelection = { type: 'regions', region_dir_relpath: 'world/region', regions: [[0, 0]] }
  act(() => view.result.current.start({ kind: 'restore', request: { source_snapshot_id: 'snapshot', selection } }))
  await waitFor(() => expect(view.result.current.state.message).toBe('started'))
  selection.regions = [[9, 9]]
  view.rerender()
  expect(bodies).toEqual([{ source_snapshot_id: 'snapshot', selection: { type: 'regions', region_dir_relpath: 'world/region', regions: [[0, 0]] } }])
  view.unmount()
  await waitFor(() => expect(signal?.aborted).toBe(true))
  try { writer.close() } catch { /* The abort may have already closed the response. */ }
})

it('turns an incomplete restoration stream into feedback instead of reporting success', async () => {
  server.use(http.post('*/api/servers/alpha/world-restore/restore', () => new HttpResponse(event({ event_type: 'stage', percent: 20 }))))
  const { result } = renderHook(() => useRestorationStream('alpha'), { wrapper })
  act(() => result.current.start({ kind: 'restore', request: { source_snapshot_id: 'snapshot', selection: { type: 'world' } } }))
  await waitFor(() => expect(result.current.state.error).toBe('连接中断'))
  expect(result.current.state.done).toBe(false)
  expect(result.current.state.active).toBe(false)
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
