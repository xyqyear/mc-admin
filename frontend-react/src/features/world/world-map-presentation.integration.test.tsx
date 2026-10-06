import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterAll, afterEach, beforeAll, beforeEach, expect, it, vi } from 'vitest'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { Route, Routes } from 'react-router'
import { createTestClient } from '@/test/http'
import { TestProviders } from '@/test/TestProviders'
import { queryKeys } from '@/shared/http/api'
import WorldRestoreScreen from '@/features/world/restore/WorldRestoreScreen'
import ChunkPruneScreen from '@/features/world/prune/ChunkPruneScreen'

vi.mock('@/features/world/map/ServerMap', () => ({ default: ({ regionPath }: { regionPath: string }) => <div>当前地图：{regionPath}</div> }))
const server = setupServer()
const layout = { world_roots: [{ name: 'world', path: '/servers/alpha/data/world', dimensions: [
  { region_dir: '/servers/alpha/data/world/region' }, { region_dir: '/servers/alpha/data/world/DIM-1/region' },
] }] }
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterAll(() => server.close())
let client: ReturnType<typeof createTestClient>
beforeEach(() => {
  client = createTestClient()
  window.history.replaceState(null, '', '/')
  server.use(
    http.get('*/api/servers/alpha', () => HttpResponse.json({ id: 'alpha', name: 'alpha', serverType: 'vanilla' })),
    http.get('*/api/servers/alpha/status', () => HttpResponse.json({ status: 'EXISTS' })),
    http.get('*/api/servers/alpha/maintenance', () => HttpResponse.json({ maintenance: false })),
    http.get('*/api/servers/alpha/online-players', () => HttpResponse.json([])),
    http.get('*/api/servers/alpha/world-restore/layout', () => HttpResponse.json(layout)),
    http.get('*/api/servers/alpha/world-restore/dimension-labels', () => HttpResponse.json({ dimension_labels: { '.': '主世界', 'DIM-1': '下界' } })),
    http.get('*/api/servers/alpha/map/status', () => HttpResponse.json({ client_jar_present: true, palette_present: true, palette_current: true })),
    http.get('*/api/servers/alpha/map/regions', () => HttpResponse.json([[0, 0, 1]])),
    http.get('*/api/servers/alpha/claims', () => HttpResponse.json({ available: false, dimensions: [], teams: [] })),
    http.get('*/api/servers/alpha/player-locations', () => HttpResponse.json({ dimensions: [], skipped: [], players: [] })),
    http.get('*/api/servers/alpha/chunk-prune/settings', () => HttpResponse.json({ default_threshold_seconds: 30 })),
    http.get('*/api/servers/alpha/chunk-prune/state', () => HttpResponse.json({ preview: null, preview_task: null, apply_task: null })),
    http.get('*/api/snapshots/restorations/active', () => HttpResponse.json({ total: 0, restorations: [] })),
    http.post('*/api/snapshots/targets/check', () => HttpResponse.json({ allowed: true, reason: null, skipped_paths: [], skipped_count: 0 })),
    http.get('*/api/tasks', () => HttpResponse.json({ total: 0, tasks: [] })),
  )
})
afterEach(() => { client.clear(); server.resetHandlers(); window.history.replaceState(null, '', '/') })

function renderPage(page: string) {
  return render(<TestProviders client={client} route={`/server/alpha/${page}`}><Routes>
    <Route path="/server/:id/:page" element={page === 'restore' ? <WorldRestoreScreen /> : <ChunkPruneScreen />} />
  </Routes></TestProviders>)
}

it.each(['restore', 'prune'])('preserves %s dimension loading visibility and navigates when layout arrives', async page => {
  let release!: () => void
  const gate = new Promise<void>(resolve => { release = resolve })
  server.use(http.get('*/api/servers/alpha/world-restore/layout', async () => { await gate; return HttpResponse.json(layout) }))
  const view = renderPage(page)
  try {
    expect(screen.queryByText('选择维度')).toBeNull()
    expect(screen.queryByText('主世界')).toBeNull()
    expect(screen.getByRole('status', { name: 'Loading' })).toBeTruthy()
    release()
    await screen.findByText('当前地图：world/region')
    let trigger: HTMLElement | undefined
    await waitFor(() => {
      trigger = screen.getAllByRole('combobox').find(element => element.textContent?.includes('主世界'))
      expect(trigger).toBeTruthy()
    })
    if (!trigger) throw new Error('维度选择框未就绪')
    fireEvent.click(trigger)
    const option = await screen.findByRole('option', { name: '下界' })
    fireEvent.pointerDown(option, { pointerType: 'mouse' })
    fireEvent.mouseDown(option)
    fireEvent.mouseUp(option)
    fireEvent.click(option, { detail: 1 })
    await screen.findByText('当前地图：world/DIM-1/region')
    expect(new URLSearchParams(window.location.hash.slice(1)).get('dim')).toBe('world/DIM-1/region')
  } finally { release(); view.unmount() }
})

it.each(['restore', 'prune'])('shows %s layout error and a separate empty-world state', async page => {
  server.use(http.get('*/api/servers/alpha/world-restore/layout', () => HttpResponse.json({ detail: 'layout unavailable' }, { status: 503 })))
  renderPage(page)
  await screen.findByText('无法获取世界布局')
  expect(screen.queryByText('未发现世界')).toBeNull()
  server.use(http.get('*/api/servers/alpha/world-restore/layout', () => HttpResponse.json({ world_roots: [] })))
  await act(async () => { await client.invalidateQueries({ queryKey: queryKeys.worldRestore.layout('alpha') }) })
  await screen.findByText('未发现世界')
  expect(screen.queryByText('无法获取世界布局')).toBeNull()
  expect(screen.queryByText('选择维度')).toBeNull()
  expect(screen.queryByText('主世界')).toBeNull()
})

it.each(['restore', 'prune'])('preserves %s map-status error visibility', async page => {
  server.use(http.get('*/api/servers/alpha/map/status', () => HttpResponse.json({ detail: 'map unavailable' }, { status: 503 })))
  renderPage(page)
  await waitFor(() => expect(client.getQueryState(queryKeys.map.status('alpha'))?.status).toBe('error'))
  if (page === 'restore') expect(screen.getByText('无法获取地图初始化状态')).toBeTruthy()
  else expect(screen.queryByText('无法获取地图初始化状态')).toBeNull()
  expect(screen.queryByRole('button', { name: '初始化地图' })).toBeNull()
})

it.each([
  ['restore', false, true, true, '尚未下载客户端 JAR。'],
  ['prune', false, true, true, '尚未下载客户端 JAR。'],
  ['restore', true, false, true, '尚未生成调色板。'],
  ['prune', true, false, true, '尚未生成调色板。'],
  ['restore', true, true, false, '调色板已过期（版本或mods变更）。'],
  ['prune', true, true, false, '调色板已过期（版本或mods变更）。'],
] as const)('keeps %s initialization reasons and submits only a normal initialization', async (page, jar, palette, current, message) => {
  let request: URL | undefined
  server.use(
    http.get('*/api/servers/alpha/map/status', () => HttpResponse.json({ client_jar_present: jar, palette_present: palette, palette_current: current })),
    http.post('*/api/servers/alpha/map/initialize', ({ request: incoming }) => {
      request = new URL(incoming.url)
      return HttpResponse.json({ detail: '初始化暂时不可用' }, { status: 503 })
    }),
  )
  renderPage(page)
  await screen.findByText(message)
  fireEvent.click(screen.getByRole('button', { name: '初始化地图' }))
  await screen.findByRole('dialog', { name: '正在初始化地图' })
  await screen.findByText('错误: 初始化暂时不可用')
  expect(request?.searchParams.get('force')).toBe('false')
})
