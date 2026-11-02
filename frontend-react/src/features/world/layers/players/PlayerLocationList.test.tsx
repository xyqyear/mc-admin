import { fireEvent, render } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import { PlayerLocationList } from './PlayerLocationList'
import type { PlayerLocationEntry } from './contracts'

it('preserves online, dimension and case-insensitive name ordering with row navigation', () => {
  const player = (name: string, dim = 'world/region'): PlayerLocationEntry => ({
    id: name, uuid: null, id_kind: 'name', source: `${name}.dat`, storage: 'legacy_players', data_version: null,
    dimension_id: dim, region_dir_relpath: dim, pos: { x: -17, y: 64, z: -33 },
  })
  const online = { ...player('Omega', 'world/DIM-1/region'), uuid: '0123456789abcdef0123456789abcdef' }
  const players = [player('Zulu'), player('alpha'), player('Aardvark', 'world/DIM-1/region'), online]
  const onPlayerClick = vi.fn()
  const props = { data: { players, dimensions: [], skipped: [] }, isLoading: false, isError: false,
    currentDimRelpath: 'world/region', dimensionLabelByRelpath: new Map([['world/region', '主世界']]),
    profilesByUuid: new Map(), pendingProfileUuids: new Set<string>(), profileError: null, onRetryProfiles: vi.fn(),
    onlinePlayerUuids: new Set([online.uuid]), onlineOnly: false, onlineStatusLoading: false, onlineStatusAvailable: true,
    overlayVisible: true, onOverlayVisibleChange: vi.fn(), onOnlineOnlyChange: vi.fn(), onRefresh: vi.fn(), onPlayerClick }
  const view = render(<PlayerLocationList {...props} />)
  const rows = () => Array.from(view.container.querySelectorAll<HTMLButtonElement>('button[title="点击定位玩家"]'))
  expect(rows().map(row => row.querySelector('[title]')?.textContent)).toEqual(['Omega', 'alpha', 'Zulu', 'Aardvark'])
  fireEvent.click(rows()[0])
  expect(onPlayerClick).toHaveBeenCalledWith(online)
  view.rerender(<PlayerLocationList {...props} onlineOnly />)
  expect(rows()).toHaveLength(1)
  view.rerender(<PlayerLocationList {...props} onlineStatusAvailable={false} onlinePlayerUuids={new Set()} />)
  expect(rows().map(row => row.querySelector('[title]')?.textContent)).toEqual(['alpha', 'Zulu', 'Aardvark', 'Omega'])
})
