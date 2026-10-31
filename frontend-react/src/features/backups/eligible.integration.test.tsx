import { act, renderHook, waitFor } from '@testing-library/react'
import { afterAll, afterEach, beforeAll, beforeEach, expect, it, vi } from 'vitest'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { createTestClient } from '@/test/http'
import { TestProviders } from '@/test/TestProviders'
import { api } from '@/shared/http/api'
import type { SnapshotScope } from './contracts'
import { useEligibleSnapshots } from './queries'

const server = setupServer()
let client: ReturnType<typeof createTestClient>
let signals: AbortSignal[] = []
let interceptor: number
let pending: Array<() => void> = []
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterAll(() => server.close())
beforeEach(() => {
  client = createTestClient()
  signals = []
  pending = []
  interceptor = api.interceptors.request.use(config => {
    if (config.signal) signals.push(config.signal as AbortSignal)
    return config
  })
})
afterEach(() => {
  client.clear()
  pending.forEach(release => release())
  api.interceptors.request.eject(interceptor)
  server.resetHandlers()
  vi.restoreAllMocks()
})
const wrapper = ({ children }: { children: React.ReactNode }) => <TestProviders client={client}>{children}</TestProviders>
const scope: SnapshotScope = { kind: 'world', server_id: 'alpha', selection: { type: 'regions', region_dir_relpath: 'world/region', regions: [[0, 0]] } }

it('aborts an obsolete selection and closing the picker, then independently loads a reopened selection', async () => {
  const abort = vi.spyOn(XMLHttpRequest.prototype, 'abort')
  const requests: Request[] = []
  let complete = false
  server.use(http.post('*/api/snapshots/eligible', ({ request }) => {
    requests.push(request)
    if (complete) return HttpResponse.json({ snapshots: [] })
    return new Promise<Response>((resolve) => {
      pending.push(() => resolve(new HttpResponse(null, { status: 499 })))
    })
  }))
  const view = renderHook(({ selected }: { selected: SnapshotScope | null }) => useEligibleSnapshots(selected), { wrapper, initialProps: { selected: scope as SnapshotScope | null } })
  await waitFor(() => expect(requests).toHaveLength(1))
  const next: SnapshotScope = { kind: 'world', server_id: 'alpha', selection: { type: 'regions', region_dir_relpath: 'world/region', regions: [[-1, 0]] } }
  view.rerender({ selected: next })
  await waitFor(() => expect(requests).toHaveLength(2))
  expect(signals[0].aborted).toBe(true)
  view.rerender({ selected: null })
  await waitFor(() => expect(signals[1].aborted).toBe(true))
  expect(abort).toHaveBeenCalledTimes(2)
  complete = true
  view.rerender({ selected: scope })
  await waitFor(() => expect(view.result.current.data).toEqual({ snapshots: [] }))
  expect(requests).toHaveLength(3)
  expect(view.result.current.isError).toBe(false)
  view.unmount()
})

it('keeps a shared candidate request alive until its final observer closes', async () => {
  const abort = vi.spyOn(XMLHttpRequest.prototype, 'abort')
  let received = false
  server.use(http.post('*/api/snapshots/eligible', () => {
    received = true
    return new Promise<Response>((resolve) => {
      pending.push(() => resolve(new HttpResponse(null, { status: 499 })))
    })
  }))
  const first = renderHook(() => useEligibleSnapshots(scope), { wrapper })
  const second = renderHook(() => useEligibleSnapshots(scope), { wrapper })
  await waitFor(() => expect(received).toBe(true))
  act(() => first.unmount())
  expect(signals[0].aborted).toBe(false)
  expect(abort).not.toHaveBeenCalled()
  act(() => second.unmount())
  await waitFor(() => expect(signals[0].aborted).toBe(true))
  expect(abort).toHaveBeenCalledTimes(1)
})
