import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterAll, afterEach, beforeAll, beforeEach, expect, it } from 'vitest'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { useOverviewData } from '@/app/overview/useOverviewData'
import OverviewScreen from '@/app/overview/Overview'
import { useTaskCenterStore } from '@/features/tasks/panelStore'
import { useServerDetailData } from '@/features/servers/useServerDetailData'
import { queryKeys } from '@/shared/http/api'
import { createTestClient } from '@/test/http'
import { TestProviders } from '@/test/TestProviders'

const server = setupServer()
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterAll(() => server.close())
let client: ReturnType<typeof createTestClient>
let cpu = 10
let cpuReads = 0
beforeEach(() => {
  client = createTestClient(); cpu = 10; cpuReads = 0
  const info = { id: 'alpha', name: 'Alpha', serverType: 'VANILLA', maxMemoryBytes: 1024 ** 3, javaVersion: 25, gameVersion: '1.21', gamePort: 25565, rconPort: 25575 }
  server.use(
    http.get('*/api/servers/', () => HttpResponse.json([info])),
    http.get('*/api/servers/alpha', () => HttpResponse.json(info)),
    http.get('*/api/servers/alpha/status', () => HttpResponse.json({ status: 'HEALTHY' })),
    http.get('*/api/servers/alpha/maintenance', () => HttpResponse.json({ active: false })),
    http.get('*/api/user/me', () => HttpResponse.json({ id: 1, username: 'owner', role: 'OWNER' })),
    http.get('*/api/servers/alpha/cpu_percent', () => { cpuReads++; return HttpResponse.json({ cpuPercentage: cpu }) }),
    http.get('*/api/servers/alpha/memory', () => HttpResponse.json({ memoryUsageBytes: 128 })),
    http.get('*/api/servers/alpha/disk-usage', () => HttpResponse.json({ diskUsageBytes: 128, diskTotalBytes: 1024, diskAvailableBytes: 896 })),
    http.get('*/api/servers/alpha/iostats', () => HttpResponse.json({ diskReadBytes: 0, diskWriteBytes: 0, networkReceiveBytes: 0, networkSendBytes: 0 })),
    http.get('*/api/servers/alpha/restart-schedule', () => HttpResponse.json(null)),
    http.get('*/api/servers/alpha/online-players', () => HttpResponse.json([])),
    http.get('*/api/system/info', () => HttpResponse.json({ cpuPercentage: 0, cpuLoad1Min: 0, cpuLoad5Min: 0, cpuLoad15Min: 0, ramUsedGB: 1, ramTotalGB: 8 })),
    http.get('*/api/system/cpu_percent', () => HttpResponse.json({ cpuPercentage: 0 })),
    http.get('*/api/system/disk-usage', () => HttpResponse.json({ diskUsedGB: 1, diskTotalGB: 8, diskAvailableGB: 7 })),
    http.get('*/api/snapshots/usage', () => HttpResponse.json({ backupUsedGB: 1, backupTotalGB: 8, backupAvailableGB: 7 })),
  )
})

it('restores lifecycle blocking and explains maintenance in the overview row', async () => {
  server.use(http.get('*/api/servers/alpha/maintenance', () => HttpResponse.json({
    active: true, kind: 'server_restart', description: '正在重启服务器', task_id: 'restart-alpha',
  })))
  useTaskCenterStore.getState().setOpen(false)
  render(<TestProviders client={client}><OverviewScreen /></TestProviders>)
  await screen.findByText('正在重启服务器')
  for (const action of ['启动服务器', '停止服务器', '重启服务器', '下线服务器', '删除服务器']) {
    expect((screen.getByTitle(action) as HTMLButtonElement).disabled).toBe(true)
  }
  expect((screen.getByTitle('服务器详情') as HTMLButtonElement).disabled).toBe(false)
  fireEvent.click(screen.getByRole('button', { name: '查看任务' }))
  expect(useTaskCenterStore.getState().isOpen).toBe(true)
  useTaskCenterStore.getState().setOpen(false)
})
afterEach(() => { client.clear(); server.resetHandlers() })
function Overview() {
  const { enrichedServers } = useOverviewData()
  return <p>概览 CPU：{enrichedServers[0]?.cpuPercentage}</p>
}
function Detail() {
  const { cpu } = useServerDetailData('alpha')
  return <p>详情 CPU：{cpu?.cpuPercentage}</p>
}

it('reuses fresh metrics across overview/detail, refreshes both, and stops polling stopped servers', async () => {
  const view = render(<TestProviders client={client}><Overview /></TestProviders>)
  await screen.findByText('概览 CPU：10')
  view.rerender(<TestProviders client={client}><Overview /><Detail /></TestProviders>)
  await screen.findByText('详情 CPU：10')
  expect(cpuReads).toBe(1)
  cpu = 20
  await act(async () => { await client.invalidateQueries({ queryKey: queryKeys.serverRuntimes.cpu('alpha') }) })
  await screen.findByText('概览 CPU：20')
  await screen.findByText('详情 CPU：20')
  expect(cpuReads).toBe(2)
  act(() => {
    client.setQueryData(queryKeys.serverStatuses.batch(['alpha']), { alpha: 'CREATED' })
    client.setQueryData(queryKeys.serverStatuses.detail('alpha'), 'CREATED')
  })
  await waitFor(() => expect(screen.getByText('概览 CPU：')).toBeTruthy())
  await act(async () => { await client.invalidateQueries({ queryKey: queryKeys.serverRuntimes.cpu('alpha') }) })
  expect(cpuReads).toBe(2)
})

it('waits for known server status before requesting runtime metrics', async () => {
  let release!: () => void
  const ready = new Promise<void>(resolve => { release = resolve })
  let statusReads = 0
  server.use(http.get('*/api/servers/alpha/status', async () => { statusReads++; await ready; return HttpResponse.json({ status: 'HEALTHY' }) }))
  render(<TestProviders client={client}><Detail /></TestProviders>)
  await waitFor(() => expect(statusReads).toBe(1))
  expect(cpuReads).toBe(0)
  release()
  await screen.findByText('详情 CPU：10')
  expect(cpuReads).toBe(1)
})
