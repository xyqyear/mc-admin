import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterAll, afterEach, beforeAll, beforeEach, expect, it, vi } from 'vitest'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { Route, Routes } from 'react-router'
import { createTestClient } from '@/test/http'
import { TestProviders } from '@/test/TestProviders'
import WorldRestoreScreen from '@/features/world/restore/WorldRestoreScreen'
import ChunkPruneScreen from '@/features/world/prune/ChunkPruneScreen'
import { queryKeys } from '@/shared/http/api'
import type { PlayerMapProfileResponse } from '@/features/players/contracts'
import type { ServerMapView } from '@/features/world/map/ServerMap'

vi.mock('@/features/world/map/ServerMap', () => ({
  default: ({ onViewChange }: { onViewChange: (view: ServerMapView) => void }) =>
    <button onClick={() => onViewChange({ zoom: 3, cx: 80, cz: 90 })}>移动地图视角</button>,
}))

const uuid = '0123456789abcdef0123456789abcdef'
const cachedProfile: PlayerMapProfileResponse = { uuid, player_db_id: 1, current_name: '缓存玩家', avatar_base64: null, resolved: true, last_skin_update: null }
const server = setupServer()
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterAll(() => server.close())
let client: ReturnType<typeof createTestClient>
beforeEach(() => { client = createTestClient(); window.history.replaceState(null, '', '/') })
afterEach(() => { client.clear(); server.resetHandlers(); window.history.replaceState(null, '', '/') })

it.each(['restore', 'prune'])('keeps %s map controls and cached positions usable while profile errors are retried through a new stream', async (page) => {
  client.setQueryData(queryKeys.players.mapProfileByUUID(uuid), cachedProfile)
  let streams = 0
  let positions = 0
  server.use(
    http.get('*/api/servers/alpha', () => HttpResponse.json({ id: 'alpha', name: 'alpha', serverType: 'vanilla' })),
    http.get('*/api/servers/alpha/status', () => HttpResponse.json({ status: 'EXISTS' })),
    http.get('*/api/servers/alpha/online-players', () => HttpResponse.json([])),
    http.get('*/api/servers/alpha/world-restore/layout', () => HttpResponse.json({ world_roots: [{ name: 'world', path: '/servers/alpha/data/world', dimensions: [{ region_dir: '/servers/alpha/data/world/region' }] }] })),
    http.get('*/api/servers/alpha/world-restore/dimension-labels', () => HttpResponse.json({ dimension_labels: {} })),
    http.get('*/api/servers/alpha/map/status', () => HttpResponse.json({ client_jar_present: true, palette_present: true, palette_current: true })),
    http.get('*/api/servers/alpha/map/regions', () => HttpResponse.json([[0, 0, 1]])),
    http.get('*/api/servers/alpha/claims', () => HttpResponse.json({ available: false, teams: [] })),
    http.get('*/api/servers/alpha/player-locations', () => {
      positions++
      return HttpResponse.json({ dimensions: [], skipped: [], players: [{ id: uuid, id_kind: 'uuid', uuid, source: `world/playerdata/${uuid}.dat`, storage: 'playerdata', data_version: 1, dimension_id: 'minecraft:overworld', region_dir_relpath: 'world/region', pos: { x: 10, y: 64, z: 20 } }] })
    }),
    http.get('*/api/servers/alpha/chunk-prune/settings', () => HttpResponse.json({ default_threshold_seconds: 30 })),
    http.get('*/api/servers/alpha/chunk-prune/state', () => HttpResponse.json({ preview: null, preview_task: null, apply_task: null })),
    http.get('*/api/snapshots/restorations/active', () => HttpResponse.json({ total: 0, restorations: [] })),
    http.post('*/api/snapshots/targets/check', () => HttpResponse.json({ allowed: true, reason: null, skipped_paths: [], skipped_count: 0 })),
    http.post('*/api/players/profiles/stream', () => {
      streams++
      return new HttpResponse(streams === 1 ? '' : `data: ${JSON.stringify({ event_type: 'profile', profile: { ...cachedProfile, current_name: '资料已恢复' } })}\n\ndata: {"event_type":"complete","total":1,"resolved":1}\n\n`, { headers: { 'Content-Type': 'text/event-stream' } })
    }),
  )
  render(<TestProviders client={client} route={`/server/alpha/${page}`}><Routes><Route path="/server/:id/:page" element={page === 'restore' ? <WorldRestoreScreen /> : <ChunkPruneScreen />} /></Routes></TestProviders>)
  fireEvent.click(await screen.findByRole('tab', { name: '玩家位置' }))
  await screen.findByText('玩家资料加载失败：玩家资料连接已中断，请重试')
  expect(screen.getByText('缓存玩家')).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: '移动地图视角' }))
  await waitFor(() => expect(new URLSearchParams(window.location.hash.slice(1)).get('cx')).toBe('80'))
  fireEvent.click(screen.getByRole('button', { name: '重试玩家资料' }))
  await screen.findByText('资料已恢复')
  expect(streams).toBe(2)
  expect(positions).toBe(1)
  expect(screen.queryByText('玩家资料加载失败：玩家资料连接已中断，请重试')).toBeNull()
  expect(screen.getByRole('button', { name: '移动地图视角' })).toBeTruthy()
})

it.each(['restore', 'prune'])('normalizes HTTP player identities through the %s controller, cached rows and online filter', async page => {
  const compactUpper = '0123456789ABCDEF0123456789ABCDEF'
  const hyphenUpper = '01234567-89AB-CDEF-0123-456789ABCDEF'
  const profile = { ...cachedProfile, current_name: '归一缓存玩家' }
  client.setQueryData(queryKeys.players.mapProfileByUUID('0123456789abcdef0123456789abcdef'), profile)
  const profileRequests: unknown[] = []
  server.use(
    http.get('*/api/servers/alpha', () => HttpResponse.json({ id: 'alpha', name: 'alpha', serverType: 'vanilla' })),
    http.get('*/api/servers/alpha/status', () => HttpResponse.json({ status: 'EXISTS' })),
    http.get('*/api/servers/alpha/online-players', () => HttpResponse.json([{ uuid: hyphenUpper, name: '在线玩家' }, { uuid: 'LegacyName', name: '旧名称' }])),
    http.get('*/api/servers/alpha/world-restore/layout', () => HttpResponse.json({ world_roots: [{ name: 'world', path: '/servers/alpha/data/world', dimensions: [{ region_dir: '/servers/alpha/data/world/region' }] }] })),
    http.get('*/api/servers/alpha/world-restore/dimension-labels', () => HttpResponse.json({ dimension_labels: {} })),
    http.get('*/api/servers/alpha/map/status', () => HttpResponse.json({ client_jar_present: true, palette_present: true, palette_current: true })),
    http.get('*/api/servers/alpha/map/regions', () => HttpResponse.json([[0, 0, 1]])),
    http.get('*/api/servers/alpha/claims', () => HttpResponse.json({ available: false, teams: [] })),
    http.get('*/api/servers/alpha/player-locations', () => HttpResponse.json({ dimensions: [], skipped: [], players: [
      { id: compactUpper, id_kind: 'uuid', uuid: compactUpper, source: 'world/playerdata/compact.dat', storage: 'playerdata', data_version: 1, dimension_id: 'minecraft:overworld', region_dir_relpath: 'world/region', pos: { x: 1, y: 64, z: 1 } },
      { id: hyphenUpper, id_kind: 'uuid', uuid: hyphenUpper, source: 'world/playerdata/hyphen.dat', storage: 'playerdata', data_version: 1, dimension_id: 'minecraft:overworld', region_dir_relpath: 'world/region', pos: { x: 2, y: 64, z: 2 } },
      { id: hyphenUpper, id_kind: 'uuid', uuid: null, source: 'world/players/fallback.dat', storage: 'legacy_players', data_version: null, dimension_id: 'minecraft:overworld', region_dir_relpath: 'world/region', pos: { x: 3, y: 64, z: 3 } },
      { id: 'LegacyName', id_kind: 'name', uuid: 'LegacyName', source: 'world/players/LegacyName.dat', storage: 'legacy_players', data_version: null, dimension_id: 'minecraft:overworld', region_dir_relpath: 'world/region', pos: { x: 4, y: 64, z: 4 } },
    ] })),
    http.get('*/api/servers/alpha/chunk-prune/settings', () => HttpResponse.json({ default_threshold_seconds: 30 })),
    http.get('*/api/servers/alpha/chunk-prune/state', () => HttpResponse.json({ preview: null, preview_task: null, apply_task: null })),
    http.get('*/api/snapshots/restorations/active', () => HttpResponse.json({ total: 0, restorations: [] })),
    http.post('*/api/snapshots/targets/check', () => HttpResponse.json({ allowed: true, reason: null, skipped_paths: [], skipped_count: 0 })),
    http.post('*/api/players/profiles/stream', async ({ request }) => {
      profileRequests.push(await request.json())
      return new HttpResponse('data: {"event_type":"complete","total":1,"resolved":1}\n\n', { headers: { 'Content-Type': 'text/event-stream' } })
    }),
  )
  render(<TestProviders client={client} route={`/server/alpha/${page}`}><Routes><Route path="/server/:id/:page" element={page === 'restore' ? <WorldRestoreScreen /> : <ChunkPruneScreen />} /></Routes></TestProviders>)
  fireEvent.click(await screen.findByRole('tab', { name: '玩家位置' }))
  await screen.findByText('在线 3/4')
  expect(screen.getAllByText('归一缓存玩家')).toHaveLength(3)
  expect(screen.getAllByText('0123456789abcdef0123456789abcdef')).toHaveLength(3)
  expect(screen.getByText('LegacyName')).toBeTruthy()
  await waitFor(() => expect(profileRequests).toEqual([{ uuids: ['0123456789abcdef0123456789abcdef'] }]))
  fireEvent.click(screen.getByRole('switch', { name: '仅显示在线玩家' }))
  await waitFor(() => expect(screen.queryByText('LegacyName')).toBeNull())
  expect(screen.getAllByRole('button', { name: /归一缓存玩家/ })).toHaveLength(3)
  expect(screen.getByText('在线 3/4')).toBeTruthy()
  fireEvent.click(screen.getByRole('switch', { name: '仅显示在线玩家' }))
  await screen.findByText('LegacyName')
  expect(client.getQueryData(queryKeys.players.mapProfileByUUID('0123456789abcdef0123456789abcdef'))).toEqual(profile)
  expect(client.getQueryData(queryKeys.players.mapProfileByUUID(compactUpper))).toBeUndefined()
  expect(client.getQueryData(queryKeys.players.mapProfileByUUID(hyphenUpper))).toBeUndefined()
  expect(client.getQueryData(queryKeys.players.mapProfileByUUID('LegacyName'))).toBeUndefined()
})
