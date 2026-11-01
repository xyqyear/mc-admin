import { act, render, screen, waitFor } from '@testing-library/react'
import { focusManager, onlineManager } from '@tanstack/react-query'
import { afterAll, afterEach, beforeAll, beforeEach, expect, it, vi } from 'vitest'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { createTestClient, deferred } from '@/test/http'
import { TestProviders } from '@/test/TestProviders'
import { monitoringFixture } from '@/test/monitoring'
import { queryKeys } from '@/shared/http/api'
import { useServerMonitoring } from './queries'
import { MonitoringObserver } from './ui/MonitoringObserver'
import { SampleValue } from './ui/SampleValue'

const server = setupServer()
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterAll(() => server.close())
let client: ReturnType<typeof createTestClient>
let reads: number
beforeEach(() => {
  client = createTestClient(); reads = 0
  client.setQueryData(queryKeys.user.me(), { id: 1 })
  focusManager.setFocused(true); onlineManager.setOnline(true)
  server.use(http.get('*/api/monitoring', () => { reads++; return HttpResponse.json(monitoringFixture('HEALTHY', reads * 10)) }))
})
afterEach(() => { vi.useRealTimers(); client.clear(); server.resetHandlers(); focusManager.setFocused(undefined); onlineManager.setOnline(true) })

function Reading({ name }: { name: string }) {
  const query = useServerMonitoring('alpha')
  return <div>{name}：<SampleValue sample={query.data?.cpu_percent} failed={query.isError}>{value => `${value}%`}</SampleValue></div>
}

it('has one periodic network source for multiple consumers and pauses when hidden or offline', async () => {
  vi.useFakeTimers()
  const view = render(<TestProviders client={client}><MonitoringObserver userId={1} /><Reading name="总览" /><Reading name="侧栏" /><Reading name="详情" /></TestProviders>)
  await act(async () => { await vi.advanceTimersByTimeAsync(100) })
  expect(screen.getAllByText('10%', { selector: 'span' })).toHaveLength(3)
  expect(reads).toBe(1)
  await act(async () => { await vi.advanceTimersByTimeAsync(2100) })
  expect(reads).toBe(2)
  act(() => focusManager.setFocused(false))
  await act(async () => { await vi.advanceTimersByTimeAsync(8000) })
  expect(reads).toBe(2)
  act(() => focusManager.setFocused(true))
  await act(async () => { await vi.advanceTimersByTimeAsync(100) })
  expect(reads).toBe(3)
  act(() => onlineManager.setOnline(false))
  await act(async () => { await vi.advanceTimersByTimeAsync(8000) })
  expect(reads).toBe(3)
  act(() => onlineManager.setOnline(true))
  await act(async () => { await vi.advanceTimersByTimeAsync(100) })
  expect(reads).toBe(4)
  view.unmount()
  await act(async () => { await vi.advanceTimersByTimeAsync(8000) })
  expect(reads).toBe(4)
})

it('retains the last value with an expired indication when the HTTP read fails', async () => {
  render(<TestProviders client={client}><MonitoringObserver userId={1} /><Reading name="CPU" /></TestProviders>)
  await screen.findByText('10%')
  server.use(http.get('*/api/monitoring', () => HttpResponse.json({ detail: '读取失败' }, { status: 503 })))
  await act(async () => { await client.invalidateQueries({ queryKey: queryKeys.monitoring.all }) })
  expect(screen.getByText('10%', { exact: false })).toBeTruthy()
  expect(await screen.findByText('（数据已过期）')).toBeTruthy()
})

it('does not publish a late response into a subsequent user session', async () => {
  const oldResponse = deferred<void>()
  let requests = 0
  server.use(http.get('*/api/monitoring', async () => {
    requests++
    if (requests === 1) { await oldResponse.promise; return HttpResponse.json(monitoringFixture('HEALTHY', 99)) }
    return HttpResponse.json(monitoringFixture('HEALTHY', 20))
  }))
  const old = render(<TestProviders client={client}><MonitoringObserver userId={1} /><Reading name="旧会话" /></TestProviders>)
  await waitFor(() => expect(requests).toBe(1))
  old.unmount()
  client.clear()
  client.setQueryData(queryKeys.user.me(), { id: 2 })
  render(<TestProviders client={client}><MonitoringObserver userId={2} /><Reading name="新会话" /></TestProviders>)
  try { await screen.findByText('20%') } finally { oldResponse.resolve() }
  await act(async () => { await oldResponse.promise })
  expect(screen.queryByText('99%')).toBeNull()
  expect(client.getQueryData(queryKeys.monitoring.snapshot(1))).toBeUndefined()
})

it('shows waiting and unavailable samples without inventing zero usage', async () => {
  const snapshot = monitoringFixture()
  snapshot.servers.alpha.cpu_percent = { value: null, sampled_at: null, quality: 'pending', error: null }
  client.setQueryData(queryKeys.monitoring.snapshot(1), snapshot)
  render(<TestProviders client={client}><Reading name="CPU" /></TestProviders>)
  expect(screen.getByText('等待采样')).toBeTruthy()
  expect(screen.queryByText('0%')).toBeNull()
  await act(async () => {
    client.setQueryData(queryKeys.monitoring.snapshot(1), { ...snapshot, servers: {
      alpha: { ...snapshot.servers.alpha, cpu_percent: { value: null, sampled_at: null, quality: 'unavailable', error: 'Java 进程不可用' } },
    } })
  })
  expect(await screen.findByText('Java 进程不可用')).toBeTruthy()
})
