import L from 'leaflet'
import { render, screen, waitFor } from '@testing-library/react'
import { afterAll, afterEach, beforeAll, beforeEach, expect, it } from 'vitest'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'

import { OperationObserver } from '@/app/operations/OperationObserver'
import { useMapRegions } from '@/features/world/queries'
import { queryKeys } from '@/shared/http/api'
import type { Operation } from '@/shared/operations/contracts'
import { createTestClient } from '@/test/http'
import { createOperationFeed } from '@/test/operations'
import { TestProviders } from '@/test/TestProviders'
import { ServerMapTileLayer } from './ServerMapTileLayer'

const server = setupServer()
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterAll(() => server.close())

let client: ReturnType<typeof createTestClient>
let feed: ReturnType<typeof createOperationFeed>
let mtime: number
let regionReads: number

beforeEach(() => {
  client = createTestClient()
  feed = createOperationFeed()
  mtime = 100
  regionReads = 0
  server.use(feed.handler, http.get('*/api/servers/:serverId/map/regions', ({ params }) => {
    regionReads++
    return HttpResponse.json([[-1, 0, params.serverId === 'alpha' ? mtime : 100]])
  }))
})
afterEach(() => {
  client.clear()
  feed.close()
  server.resetHandlers()
})

function MapImage({ id }: { id: string }) {
  const { data } = useMapRegions(id, 'world/region')
  if (!data) return null
  const layer = new ServerMapTileLayer({
    serverId: id,
    regionPath: 'world/region',
    regions: new Map(data.map(([x, z, mt]) => [`${x},${z}`, mt])),
  })
  return <img alt={id} src={layer.getTileUrl(Object.assign(L.point(-1, 0), { z: 0 }))} />
}

function Shell({ visible = true }: { visible?: boolean }) {
  return <TestProviders client={client}>
    <OperationObserver sessionId="owner" />
    {visible && <><MapImage id="alpha" /><MapImage id="beta" /></>}
  </TestProviders>
}

const src = (id: string) => screen.getByRole('img', { name: id }).getAttribute('src')!
async function drained() {
  await waitFor(() => expect(client.getQueryData(queryKeys.operations.checkpoint('owner')))
    .toEqual({ cursor: feed.cursor, active_count: 0 }))
}
async function ready() {
  await drained()
  await screen.findByRole('img', { name: 'alpha' })
  await screen.findByRole('img', { name: 'beta' })
}

it('reuses tile URLs after a fresh page load and operation-feed reset when the world is unchanged', async () => {
  const view = render(<Shell />)
  await ready()
  const before = src('alpha')
  const reads = regionReads

  feed.restart()
  await drained()
  await waitFor(() => expect(regionReads).toBeGreaterThan(reads))
  expect(src('alpha')).toBe(before)

  view.unmount()
  client.clear()
  client = createTestClient()
  render(<Shell />)
  await ready()
  expect(src('alpha')).toBe(before)
  expect(Object.fromEntries(new URL(src('alpha')).searchParams))
    .toEqual({ region: 'world/region', mt: '100' })
})

it.each(['succeeded', 'failed', 'cancelled'])('reads changed timestamps after an off-page restore becomes %s', async state => {
  const view = render(<Shell />)
  await ready()
  const before = src('alpha')
  const other = src('beta')
  client.setQueryData(queryKeys.snapshots.history('alpha'), { total: 0, restorations: [] })
  view.rerender(<Shell visible={false} />)
  mtime = 101
  const operation: Operation = {
    operation_id: 'restore', kind: 'snapshot_restore', state, data_changed: true,
    updated_at: '2026-09-30T01:00:00Z', ended_at: '2026-09-30T01:00:00Z',
    resources: [{ kind: 'files', server_id: 'alpha', generation: 1, path: '' }],
  }
  feed.publish(operation)
  await drained()
  expect(client.getQueryState(queryKeys.snapshots.history('alpha'))?.isInvalidated).toBe(true)

  view.rerender(<Shell />)
  await waitFor(() => expect(new URL(src('alpha')).searchParams.get('mt')).toBe('101'))
  expect(src('alpha')).not.toBe(before)
  expect(src('beta')).toBe(other)

  const reads = regionReads
  const restored = src('alpha')
  feed.publish({ ...operation, operation_id: 'preview', kind: 'snapshot_preview', data_changed: false })
  await drained()
  expect(regionReads).toBe(reads)
  expect(src('alpha')).toBe(restored)
})
