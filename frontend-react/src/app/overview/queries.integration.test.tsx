import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterAll, afterEach, beforeAll, beforeEach, expect, it } from 'vitest'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { useOverviewData } from './useOverviewData'
import OverviewScreen from './Overview'
import ServerMenuIcon from '@/app/layout/ServerMenuIcon'
import { useTaskCenterStore } from '@/features/tasks/panelStore'
import { useServerDetailData } from '@/features/servers/useServerDetailData'
import { MonitoringObserver } from '@/features/monitoring/ui/MonitoringObserver'
import { queryKeys } from '@/shared/http/api'
import { createTestClient, deferred } from '@/test/http'
import { TestProviders } from '@/test/TestProviders'
import { monitoringFixture } from '@/test/monitoring'

const server = setupServer()
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterAll(() => server.close())
let client: ReturnType<typeof createTestClient>
let snapshot = monitoringFixture()
let reads = 0
beforeEach(() => {
  client = createTestClient(); snapshot = monitoringFixture(); reads = 0
  client.setQueryData(queryKeys.user.me(), { id: 1, username: 'owner', role: 'OWNER' })
  const info = { id: 'alpha', name: 'Alpha', server_generation: 1, serverType: 'VANILLA', maxMemoryBytes: 1024 ** 3, javaVersion: 25, gameVersion: '1.21', gamePort: 25565, rconPort: 25575 }
  server.use(
    http.get('*/api/servers/', () => HttpResponse.json([info])),
    http.get('*/api/servers/alpha', () => HttpResponse.json(info)),
    http.get('*/api/monitoring', () => { reads++; return HttpResponse.json(snapshot) }),
    http.get('*/api/servers/alpha/restart-schedule', () => HttpResponse.json(null)),
    http.get('*/api/servers/alpha/online-players', () => HttpResponse.json([])),
    http.get('*/api/snapshots/usage', () => HttpResponse.json({ backupUsedGB: 1, backupTotalGB: 8, backupAvailableGB: 7 })),
  )
})
afterEach(() => { client.clear(); server.resetHandlers() })
function Overview() {
  const { enrichedServers } = useOverviewData()
  return <p>概览 CPU：{enrichedServers[0]?.samples?.cpu_percent.value}</p>
}
function Detail() {
  const { samples } = useServerDetailData('alpha')
  return <p>详情 CPU：{samples?.cpu_percent.value}</p>
}

it('restores lifecycle blocking and explains maintenance in the overview row', async () => {
  snapshot.servers.alpha.maintenance = { active: true, kind: 'server_restart', description: '正在重启服务器', task_id: 'restart-alpha' }
  useTaskCenterStore.getState().setOpen(false)
  render(<TestProviders client={client}><MonitoringObserver userId={1} /><OverviewScreen /></TestProviders>)
  await screen.findByText('正在重启服务器')
  for (const action of ['启动服务器', '停止服务器', '重启服务器', '下线服务器', '删除服务器']) {
    expect((screen.getByTitle(action) as HTMLButtonElement).disabled).toBe(true)
  }
  expect(screen.getByRole('link', { name: '服务器详情' }).getAttribute('href')).toBe('/server/alpha')
  fireEvent.click(screen.getByRole('button', { name: '查看任务' }))
  expect(useTaskCenterStore.getState().isOpen).toBe(true)
  useTaskCenterStore.getState().setOpen(false)
})

it('shares one monitoring read across overview, sidebar and detail and removes stopped CPU values', async () => {
  const view = render(<TestProviders client={client}><MonitoringObserver userId={1} /><Overview /><ServerMenuIcon serverId="alpha" /></TestProviders>)
  await screen.findByText('概览 CPU：10')
  view.rerender(<TestProviders client={client}><MonitoringObserver userId={1} /><Overview /><ServerMenuIcon serverId="alpha" /><Detail /></TestProviders>)
  await screen.findByText('详情 CPU：10')
  expect(reads).toBe(1)
  snapshot = monitoringFixture('HEALTHY', 20)
  await act(async () => { await client.invalidateQueries({ queryKey: queryKeys.monitoring.all }) })
  await screen.findByText('概览 CPU：20')
  await screen.findByText('详情 CPU：20')
  expect(reads).toBe(2)
  snapshot = monitoringFixture('CREATED')
  await act(async () => { await client.invalidateQueries({ queryKey: queryKeys.monitoring.all }) })
  await waitFor(() => expect(screen.getByText('概览 CPU：')).toBeTruthy())
  expect(screen.getByText('详情 CPU：')).toBeTruthy()
  expect(reads).toBe(3)
})

it('keeps missing samples unknown until the shared observation arrives', async () => {
  const release = deferred<void>()
  server.use(http.get('*/api/monitoring', async () => { reads++; await release.promise; return HttpResponse.json(snapshot) }))
  render(<TestProviders client={client}><MonitoringObserver userId={1} /><Detail /></TestProviders>)
  try {
    await waitFor(() => expect(reads).toBe(1))
    expect(screen.getByText('详情 CPU：')).toBeTruthy()
  } finally { release.resolve() }
  await screen.findByText('详情 CPU：10')
  expect(reads).toBe(1)
})

it('shows players only while the shared status confirms Minecraft is healthy', async () => {
  let playerReads = 0
  server.use(http.get('*/api/servers/alpha/online-players', () => {
    playerReads++
    return HttpResponse.json([{ current_name: 'Notch' }])
  }))
  render(<TestProviders client={client}><MonitoringObserver userId={1} /><OverviewScreen /></TestProviders>)
  await screen.findByText('Notch')
  expect(playerReads).toBe(1)
  snapshot = monitoringFixture('CREATED')
  await act(async () => { await client.invalidateQueries({ queryKey: queryKeys.monitoring.all }) })
  await waitFor(() => expect(screen.queryByText('Notch')).toBeNull())
  expect(playerReads).toBe(1)
})
