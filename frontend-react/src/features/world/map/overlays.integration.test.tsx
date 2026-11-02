import { StrictMode, useMemo } from 'react'
import L from 'leaflet'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, waitFor } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import { ServerMap, type ServerMapOverlay } from './ServerMap'
import { usePlayersOverlay } from '../layers/players/usePlayersOverlay'
import type { PlayerMapProfileResponse } from '@/features/players/contracts'
import type { PlayerLocationEntry } from '../layers/players/contracts'

const uuid = '0123456789abcdef0123456789abcdef'
const players: PlayerLocationEntry[] = [{ id: uuid, uuid, id_kind: 'uuid', source: 'first.dat', storage: 'playerdata',
  data_version: 1, dimension_id: 'minecraft:overworld', region_dir_relpath: 'world/region', pos: { x: 0, y: 64, z: 0 } }]
const regions = new Map<string, number>()
const online = new Set<string>()
const profile = (name: string): PlayerMapProfileResponse => ({ uuid, player_db_id: 1, current_name: name, avatar_base64: null, resolved: true, last_skin_update: null })

it('retains unrelated overlay DOM and player layers across profile and visibility updates in StrictMode', () => {
  const renderClaims = vi.fn(() => L.marker([0, 0], { icon: L.divIcon({ html: '<button>领地</button>', className: 'test-claim-label' }) }))
  const claim: ServerMapOverlay = { id: 'claims', render: renderClaims }
  function Screen({ name, visible = true, claims = true }: { name: string; visible?: boolean; claims?: boolean }) {
    const profiles = useMemo(() => new Map([[uuid, profile(name)]]), [name])
    const { overlays: playerOverlays } = usePlayersOverlay({ players, profilesByUuid: profiles, onlinePlayerUuids: online,
      currentDimRelpath: 'world/region', onlineOnly: false, onlineStatusAvailable: true, enabled: true, visible })
    const overlays = useMemo(() => [...(claims ? [claim] : []), ...(playerOverlays ?? [])], [claims, playerOverlays])
    return <ServerMap serverId="mock" regionPath="world/region" regions={regions} overlays={overlays} />
  }
  const client = new QueryClient()
  const shell = (name: string, visible = true, claims = true) => <StrictMode><QueryClientProvider client={client}><Screen name={name} visible={visible} claims={claims} /></QueryClientProvider></StrictMode>
  const view = render(shell('原名'))
  const label = view.container.querySelector('.test-claim-label')
  const marker = view.container.querySelector('.player-location-icon')
  expect(label).toBeTruthy()
  expect(marker?.textContent).toContain('原名')
  const initialClaimRenders = renderClaims.mock.calls.length
  view.rerender(shell('新名'))
  expect(view.container.querySelector('.test-claim-label')).toBe(label)
  expect(view.container.querySelector('.player-location-icon')).toBe(marker)
  expect(marker?.textContent).toContain('新名')
  expect(renderClaims).toHaveBeenCalledTimes(initialClaimRenders)
  view.rerender(shell('新名', false))
  expect(view.container.querySelector('.player-location-icon')).toBeNull()
  expect(view.container.querySelector('.test-claim-label')).toBe(label)
  view.rerender(shell('新名', true, false))
  expect(view.container.querySelector('.test-claim-label')).toBeNull()
  expect(view.container.querySelector('.player-location-icon')?.textContent).toContain('新名')
  view.unmount()
  expect(view.container.querySelector('.leaflet-pane')).toBeNull()
  client.clear()
})

it('replaces a changed overlay after removing its old layer and drops all disabled overlays', async () => {
  const client = new QueryClient()
  let map: L.Map | undefined
  const original = L.marker([0, 0], { icon: L.divIcon({ className: 'original-label' }) })
  const first: ServerMapOverlay = { id: 'claims', render: m => { map = m; return original } }
  const replacement: ServerMapOverlay = { id: 'claims', render: m => {
    expect(m.hasLayer(original)).toBe(false)
    m.setView([33, -17], 0, { animate: false })
    return L.marker([33, -17], { icon: L.divIcon({ className: 'replacement-label' }) })
  } }
  const shell = (overlays?: ServerMapOverlay[]) => <QueryClientProvider client={client}><ServerMap serverId="mock" regionPath="world/region" regions={regions} overlays={overlays} /></QueryClientProvider>
  const view = render(shell([first]))
  view.rerender(shell([replacement]))
  expect(view.container.querySelector('.original-label')).toBeNull()
  expect(view.container.querySelector('.replacement-label')).toBeTruthy()
  await waitFor(() => expect(map!.getCenter()).toEqual(L.latLng(33, -17)))
  view.rerender(shell())
  expect(view.container.querySelector('.replacement-label')).toBeNull()
  view.unmount()
  client.clear()
})
