import { act, fireEvent, render, renderHook, screen, waitFor } from '@testing-library/react'
import { afterAll, afterEach, beforeAll, beforeEach, expect, it, vi } from 'vitest'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { createTestClient } from '@/test/http'
import { TestProviders } from '@/test/TestProviders'
import { queryKeys } from '@/shared/http/api'
import { useChunkPruneController } from '@/features/world/prune/useChunkPruneController'
import { useWorldRestoreController } from '@/features/world/restore/useWorldRestoreController'
import type { BackgroundTaskResponse } from '@/features/tasks/contracts';
import type { ChunkPrunePreview } from '@/features/world/prune/contracts'
import type L from 'leaflet'
import type { FtbClusterEntry } from '@/features/world/layers/claims/contracts'
import type { PlayerLocationEntry } from '@/features/world/layers/players/contracts'

const server = setupServer()
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterAll(() => server.close())
let client: ReturnType<typeof createTestClient>
let preview: ChunkPrunePreview
let previewTask: BackgroundTaskResponse
let applyTask: BackgroundTaskResponse | null
let cancels: number
beforeEach(() => {
  client = createTestClient(); cancels = 0; applyTask = null
  window.history.replaceState(null, '', '/#dim=world%2Fregion&mode=regions&z=2&cx=10&cz=-20')
  preview = { task_id: 'preview', input_version: 'v1', expires_at: null, availability: 'ready', apply_task_id: null }
  previewTask = { task_id: 'preview', task_type: 'chunk_prune_preview', name: 'preview', status: 'completed', progress: 100, message: 'ready', server_id: 'alpha', created_at: new Date().toISOString(), cancellable: false, result: { mode: 'regions', dry_run: true, threshold_seconds: 30, regions_selected: 1 } }
  server.use(
    http.get('*/api/servers/alpha', () => HttpResponse.json({ id: 'alpha', name: 'alpha', serverType: 'vanilla' })),
    http.get('*/api/servers/alpha/status', () => HttpResponse.json({ status: 'EXISTS' })),
    http.get('*/api/servers/alpha/online-players', () => HttpResponse.json([])),
    http.get('*/api/servers/alpha/world-restore/layout', () => HttpResponse.json({ world_roots: [{ name: 'world', path: '/servers/alpha/data/world', dimensions: [{ region_dir: '/servers/alpha/data/world/region' }, { region_dir: '/servers/alpha/data/world/DIM-1/region' }] }] })),
    http.get('*/api/servers/alpha/world-restore/dimension-labels', () => HttpResponse.json({ dimension_labels: {} })),
    http.get('*/api/servers/alpha/map/status', () => HttpResponse.json({ client_jar_present: true, palette_present: true, palette_current: true })),
    http.get('*/api/servers/alpha/map/regions', () => HttpResponse.json([[0, 0, 1]])),
    http.get('*/api/servers/alpha/claims', () => HttpResponse.json({ available: false, teams: [] })),
    http.get('*/api/servers/alpha/player-locations', () => HttpResponse.json({ players: [] })),
    http.get('*/api/servers/alpha/chunk-prune/settings', () => HttpResponse.json({ default_threshold_seconds: 30 })),
    http.get('*/api/servers/alpha/chunk-prune/state', () => HttpResponse.json({ preview, preview_task: previewTask, apply_task: applyTask })),
    http.get('*/api/servers/alpha/chunk-prune/previews/preview/geometry', () => HttpResponse.json({ dimensions: [] })),
    http.post('*/api/tasks/:id/cancel', () => { cancels++; return HttpResponse.json({}) }),
  )
})
afterEach(() => { client.clear(); server.resetHandlers(); window.history.replaceState(null, '', '/') })
const wrapper = ({ children }: { children: React.ReactNode }) => <TestProviders client={client}>{children}</TestProviders>

it.each(['expired', 'stale', 'consumed', 'unavailable'] as const)('keeps historical preview results but requires regeneration when %s', async availability => {
  preview.availability = availability
  const { result } = renderHook(() => useChunkPruneController('alpha'), { wrapper })
  await waitFor(() => expect(result.current.previewStatus).toBe('completed'))
  expect(result.current.previewResult?.regions_selected).toBe(1)
  expect(result.current.canApply).toBe(false)
  expect(result.current.canPreview).toBe(true)
  expect(result.current.previewError).toContain('重新生成预览')
})

it('shows synchronous stale errors, disables resubmission and preserves controls for a new preview', async () => {
  let applies = 0
  server.use(http.post('*/api/servers/alpha/chunk-prune/apply', () => {
    applies++; return HttpResponse.json({ detail: { code: 'prune_preview_stale', message: '世界文件已变化，请重新生成预览' } }, { status: 409 })
  }))
  function Controls() {
    const state = useChunkPruneController('alpha')
    return <><button disabled={!state.canApply} onClick={state.startApply}>提交删除</button><span>{state.applyError}</span><span>阈值：{state.thresholdSeconds}</span>{state.confirmDialog}</>
  }
  render(<Controls />, { wrapper })
  await waitFor(() => expect((screen.getByText('提交删除') as HTMLButtonElement).disabled).toBe(false))
  fireEvent.click(screen.getByText('提交删除'))
  fireEvent.click(screen.getByRole('button', { name: '删除区块' }))
  await screen.findByText('世界文件已变化，请重新生成预览')
  expect((screen.getByText('提交删除') as HTMLButtonElement).disabled).toBe(true)
  expect(screen.getByText('阈值：30')).toBeTruthy()
  expect(applies).toBe(1)
})

it('retains feature-owned preview projections after generic task dismissal and never cancels on navigation', async () => {
  const first = renderHook(() => useChunkPruneController('alpha'), { wrapper })
  await waitFor(() => expect(first.result.current.canApply).toBe(true))
  first.unmount()
  client.removeQueries({ queryKey: ['tasks'] })
  const next = renderHook(() => useChunkPruneController('alpha'), { wrapper })
  await waitFor(() => expect(next.result.current.canApply).toBe(true))
  applyTask = { ...previewTask, task_id: 'apply', task_type: 'chunk_prune_apply', status: 'running' }
  await act(async () => { await client.invalidateQueries({ queryKey: queryKeys.chunkPrune.state('alpha') }) })
  await waitFor(() => expect(next.result.current.canApply).toBe(false))
  next.unmount()
  expect(cancels).toBe(0)
})

it('blocks reuse after an accepted apply fails its final input check', async () => {
  preview.apply_task_id = 'apply'
  applyTask = { ...previewTask, task_id: 'apply', task_type: 'chunk_prune_apply', status: 'failed', error: '保护范围已变化，请重新预览', error_code: 'prune_preview_stale' }
  const { result } = renderHook(() => useChunkPruneController('alpha'), { wrapper })
  await waitFor(() => expect(result.current.applyStatus).toBe('failed'))
  expect(result.current.canApply).toBe(false)
  expect(result.current.applyError).toBe('保护范围已变化，请重新预览')
})

it('preserves view coordinates in the URL and resets selection on a dimension change', async () => {
  window.history.replaceState(null, '', '/#dim=world%2Fregion&mode=region&z=2&cx=10&cz=-20')
  const { result } = renderHook(() => useWorldRestoreController('alpha'), { wrapper })
  await waitFor(() => expect(result.current.map.regionRelpath).toBe('world/region'))
  expect(result.current.map.initialView).toEqual({ zoom: 2, cx: 10, cz: -20 })
  act(() => result.current.handleSelectionChange(new Set(['0,0'])))
  expect(result.current.selection.size).toBe(1)
  act(() => result.current.map.handleViewChange({ zoom: 3, cx: 80, cz: 90 }))
  await waitFor(() => expect(new URLSearchParams(window.location.hash.slice(1)).get('cx')).toBe('80'))
  act(() => result.current.map.handleDimensionChange('world/DIM-1/region'))
  await waitFor(() => expect(result.current.map.regionRelpath).toBe('world/DIM-1/region'))
  expect(result.current.selection.size).toBe(0)
  expect(new URLSearchParams(window.location.hash.slice(1)).has('cx')).toBe(false)
})

it.each(['claims', 'players'] as const)('maps negative %s locations and consumes cross-dimension pans through real overlays', async kind => {
  window.history.replaceState(null, '', '/#dim=world%2Fregion&mode=chunk&z=2&cx=10&cz=-20')
  const clusters: FtbClusterEntry[] = [
    { id: 'same', region_dir_relpath: 'world/region', chunks: [[-2, -3]], force_loaded: [], centroid_block: [-17, -33], bbox_chunk: [-2, -3, -2, -3], regions: [[-1, -1]] },
    { id: 'cross', region_dir_relpath: 'world/DIM-1/region', chunks: [[-2, -3]], force_loaded: [], centroid_block: [-17, -33], bbox_chunk: [-2, -3, -2, -3], regions: [[-1, -1]] },
  ]
  const players: PlayerLocationEntry[] = [
    { id: '0123456789abcdef0123456789abcdef', id_kind: 'uuid', uuid: '0123456789abcdef0123456789abcdef', source: 'world/playerdata/same.dat', storage: 'playerdata', data_version: 1, dimension_id: 'minecraft:overworld', region_dir_relpath: 'world/region', pos: { x: -17, y: 64, z: -33 } },
    { id: '0123456789abcdef0123456789abcdef', id_kind: 'uuid', uuid: '0123456789abcdef0123456789abcdef', source: 'world/playerdata/cross.dat', storage: 'playerdata', data_version: 1, dimension_id: 'minecraft:the_nether', region_dir_relpath: 'world/DIM-1/region', pos: { x: -17, y: 64, z: -33 } },
  ]
  server.use(
    http.get('*/api/servers/alpha/claims', () => HttpResponse.json({ available: true, dimensions: [], teams: [{ id: 'team', display_name: '负坐标领地', type: 'party', members: [], owner: null, total_chunks: 2, clusters }] })),
    http.get('*/api/servers/alpha/player-locations', () => HttpResponse.json({ dimensions: [], skipped: [], players })),
    http.post('*/api/players/profiles/stream', () => new HttpResponse('data: {"event_type":"complete","total":1,"resolved":0}\n\n', { headers: { 'Content-Type': 'text/event-stream' } })),
  )
  const { result } = renderHook(() => useWorldRestoreController('alpha'), { wrapper })
  await waitFor(() => expect(result.current.claims.teams).toHaveLength(1))
  await waitFor(() => expect(result.current.players.playerLocationsQ.data?.players).toHaveLength(2))
  const panTo = vi.fn()
  const setView = vi.fn()
  const leafletMap = { panTo, setView, getZoom: () => 5 } as unknown as L.Map
  const initialOverlay = kind === 'claims' ? result.current.claims.claimsOverlays![0] : result.current.players.playersOverlays![0]
  initialOverlay.render(leafletMap)
  act(() => result.current.handleSelectionChange(new Set(['-2,-3'])))
  act(() => {
    if (kind === 'claims') result.current.claims.handleClusterClick(result.current.claims.teams[0].clusters[0])
    else result.current.players.handlePlayerClick(result.current.players.playerLocationsQ.data!.players[0])
  })
  expect(panTo).toHaveBeenCalledExactlyOnceWith([33, -17])
  expect(setView).not.toHaveBeenCalled()
  expect(result.current.urlMode).toBe('chunk')
  expect([...result.current.selection]).toEqual(['-2,-3'])
  expect(new URLSearchParams(window.location.hash.slice(1)).get('cx')).toBe('10')
  act(() => {
    if (kind === 'claims') result.current.claims.handleClusterClick(result.current.claims.teams[0].clusters[1])
    else result.current.players.handlePlayerClick(result.current.players.playerLocationsQ.data!.players[1])
  })
  await waitFor(() => expect(result.current.map.regionRelpath).toBe('world/DIM-1/region'))
  expect(result.current.urlMode).toBe('chunk')
  expect(result.current.selection.size).toBe(0)
  const changedDimension = new URLSearchParams(window.location.hash.slice(1))
  expect(changedDimension.get('dim')).toBe('world/DIM-1/region')
  expect(changedDimension.get('mode')).toBe('chunk')
  expect(changedDimension.has('z')).toBe(false)
  expect(changedDimension.has('cx')).toBe(false)
  expect(changedDimension.has('cz')).toBe(false)
  initialOverlay.render(leafletMap)
  expect(setView).not.toHaveBeenCalled()
  const newOverlay = kind === 'claims' ? result.current.claims.claimsOverlays![0] : result.current.players.playersOverlays![0]
  await act(async () => { newOverlay.render(leafletMap) })
  expect(setView).toHaveBeenCalledExactlyOnceWith([33, -17], 5, { animate: false })
  act(() => result.current.map.handleViewChange({ zoom: 5, cx: -17, cz: -33 }))
  const located = new URLSearchParams(window.location.hash.slice(1))
  expect(located.get('dim')).toBe('world/DIM-1/region')
  expect(located.get('mode')).toBe('chunk')
  expect(located.get('z')).toBe('5')
  expect(located.get('cx')).toBe('-17')
  expect(located.get('cz')).toBe('-33')
  await act(async () => { newOverlay.render(leafletMap) })
  expect(setView).toHaveBeenCalledTimes(1)
  expect(panTo).toHaveBeenCalledTimes(1)
})
