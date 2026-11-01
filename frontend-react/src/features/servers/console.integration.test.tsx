import { useEffect, useImperativeHandle, useMemo, useRef, forwardRef } from 'react'
import { act, render, waitFor } from '@testing-library/react'
import { afterAll, afterEach, beforeAll, beforeEach, expect, it, vi } from 'vitest'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { Route, Routes } from 'react-router'
import { createTestClient, deferred } from '@/test/http'
import { TestProviders } from '@/test/TestProviders'
import { queryKeys } from '@/shared/http/api'
import { MonitoringObserver } from '@/features/monitoring/ui/MonitoringObserver'
import { monitoringFixture } from '@/test/monitoring'
import type { ServerTerminalProps, ServerTerminalRef } from './ui/ServerTerminal'
import ServerConsole from './ServerConsoleScreen'

vi.mock('./ui/ServerOperationButtons', () => ({ default: () => null }))
vi.mock('./ui/ServerTerminal', () => ({ default: forwardRef<ServerTerminalRef, ServerTerminalProps>(({ onReady }, ref) => {
  const terminal = useMemo(() => ({ clear: vi.fn(), write: vi.fn(), fit: vi.fn(), getSize: () => ({ cols: 80, rows: 24 }), onMessage: vi.fn() }), [])
  const ready = useRef(onReady)
  useEffect(() => { ready.current = onReady }, [onReady])
  useImperativeHandle(ref, () => terminal)
  useEffect(() => { ready.current?.(terminal) }, [terminal])
  return <div>terminal ready</div>
}) }))

class Socket {
  static CONNECTING = 0
  static OPEN = 1
  static instances: Socket[] = []
  readyState = 0
  onopen: (() => void) | null = null
  onclose: ((event: { code: number; reason: string }) => void) | null = null
  onerror = null
  onmessage = null
  close = vi.fn(() => { this.readyState = 3 })
  constructor(readonly url: string) { Socket.instances.push(this) }
  open() { this.readyState = 1; this.onopen?.() }
}
const server = setupServer()
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterAll(() => server.close())
let client: ReturnType<typeof createTestClient>
beforeEach(() => { client = createTestClient(); client.setQueryData(queryKeys.user.me(), { id: 1 }); Socket.instances = []; vi.stubGlobal('WebSocket', Socket) })
afterEach(() => { client.clear(); server.resetHandlers(); vi.unstubAllGlobals() })
function mount() {
  return render(<TestProviders client={client} route="/server/alpha/console"><MonitoringObserver userId={1} /><Routes><Route path="/server/:id/console" element={<ServerConsole />} /></Routes></TestProviders>)
}

it.each(['delayed', 'cached'])('connects once when terminal and %s server responses become ready, and closes on ineligible state and unmount', async mode => {
  const release = deferred<void>()
  server.use(
    http.get('*/api/servers/alpha', async () => { await release.promise; return HttpResponse.json({ id: 'alpha', name: 'alpha', serverType: 'VANILLA', javaVersion: 25, gameVersion: '1.21.11', gamePort: 25565, rconPort: 25575, maxMemoryBytes: 1024 }) }),
    http.get('*/api/monitoring', async () => { await release.promise; return HttpResponse.json(monitoringFixture()) }),
  )
  if (mode === 'cached') {
    client.setQueryData(queryKeys.serverInfos.detail('alpha'), { name: 'alpha' })
    client.setQueryData(queryKeys.monitoring.snapshot(1), monitoringFixture('HEALTHY'))
    release.resolve()
  }
  const view = mount()
  if (mode === 'delayed') expect(Socket.instances).toHaveLength(0)
  await act(async () => { release.resolve() })
  await waitFor(() => expect(Socket.instances).toHaveLength(1))
  const first = Socket.instances[0]!
  expect(first.close).not.toHaveBeenCalled()
  act(() => first.open())
  await act(async () => { client.setQueryData(queryKeys.monitoring.snapshot(1), monitoringFixture('HEALTHY')) })
  expect(Socket.instances).toHaveLength(1)
  await act(async () => { client.setQueryData(queryKeys.monitoring.snapshot(1), monitoringFixture('CREATED')) })
  await waitFor(() => expect(first.close).toHaveBeenCalledTimes(1))
  await act(async () => { client.setQueryData(queryKeys.monitoring.snapshot(1), monitoringFixture('HEALTHY')) })
  await waitFor(() => expect(Socket.instances).toHaveLength(2))
  view.unmount()
  expect(Socket.instances[1]!.close).toHaveBeenCalledTimes(1)
})
