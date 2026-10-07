import L from 'leaflet'
import { act, render, screen, waitFor } from '@testing-library/react'
import { afterAll, afterEach, beforeAll, beforeEach, expect, it } from 'vitest'
import { setupServer } from 'msw/node'
import { createTestClient } from '@/test/http'
import { createOperationFeed } from '@/test/operations'
import { TestProviders } from '@/test/TestProviders'
import { queryKeys } from '@/shared/http/api'
import type { Operation } from '@/shared/operations/contracts'
import { OperationObserver } from '@/app/operations/OperationObserver'
import { ServerMapTileLayer } from './ServerMapTileLayer'
import { useMapRevision } from './revision'

const server = setupServer()
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterAll(() => server.close())
let client: ReturnType<typeof createTestClient>
let feed: ReturnType<typeof createOperationFeed>
beforeEach(() => { client = createTestClient(); feed = createOperationFeed(); server.use(feed.handler) })
afterEach(() => { client.clear(); server.resetHandlers() })
function MapImage({ id }: { id: string }) {
  const revision = useMapRevision(id)
  const layer = new ServerMapTileLayer({ serverId: id, regionPath: 'world/region', regions: new Map([['-1,0', 100]]), revision })
  return <img alt={id} src={layer.getTileUrl(Object.assign(L.point(-1, 0), { z: 0 }))} />
}
function Shell({ visible = true }: { visible?: boolean }) {
  return <TestProviders client={client}><OperationObserver sessionId="owner" />{visible && <><MapImage id="alpha" /><MapImage id="beta" /></>}</TestProviders>
}
const src = (id: string) => screen.getByRole('img', { name: id }).getAttribute('src')!
function operation(id: string, state: string, time: string, global = false): Operation {
  return { operation_id: id, kind: 'snapshot_restore', state, data_changed: state !== 'running',
    updated_at: time, ended_at: state === 'running' ? null : time,
    resources: [{ kind: 'files', server_id: global ? null : 'alpha', generation: global ? null : 1, path: '' }] }
}
async function poll() { await act(async () => { await client.refetchQueries({ queryKey: queryKeys.operations.session('owner'), exact: true }) }) }
async function ready() { await waitFor(() => expect(client.getQueryData(queryKeys.operations.session('owner'))).toBeTruthy()) }

it.each(['succeeded', 'failed', 'cancelled'])('refreshes same-mtime tiles after an unmounted restore becomes %s, without changing other servers', async state => {
  const view = render(<Shell />); await ready()
  const before = src('alpha'), other = src('beta')
  client.setQueryData(queryKeys.snapshots.history('alpha'), { total: 0, restorations: [] })
  view.rerender(<Shell visible={false} />)
  feed.publish(operation('restore', state, '2026-09-30T01:01:00Z'))
  await poll()
  expect(client.getQueryState(queryKeys.snapshots.history('alpha'))?.isInvalidated).toBe(true)
  view.rerender(<Shell />)
  await waitFor(() => expect(src('alpha')).not.toBe(before))
  expect(new URL(src('alpha')).searchParams.get('mt')).toBe('100')
  expect(src('beta')).toBe(other)
  const restored = src('alpha')
  feed.publish({ ...operation('preview', 'succeeded', '2026-09-30T01:02:00Z'), kind: 'snapshot_preview', data_changed: false })
  await poll()
  expect(src('alpha')).toBe(restored)
})

it('uses notification order for new changes despite clock rollback or a repeated terminal operation', async () => {
  render(<Shell />); await ready()
  feed.publish(operation('global', 'succeeded', '2099-09-30T02:00:00Z', true))
  await poll()
  await waitFor(() => expect(new URL(src('alpha')).searchParams.get('revision')).toContain('global'))
  const global = src('alpha'), other = src('beta')
  expect(new URL(global).searchParams.get('revision')).toContain('global')
  feed.publish(operation('same-terminal', 'failed', '2026-09-30T01:00:00Z'))
  await poll()
  await waitFor(() => expect(src('alpha')).not.toBe(global))
  expect(src('beta')).toBe(other)
  const first = src('alpha')
  feed.publish(operation('same-terminal', 'failed', '2026-09-30T01:00:00Z'))
  await poll()
  await waitFor(() => expect(src('alpha')).not.toBe(first))
  expect(src('beta')).toBe(other)
})

it('changes every map token after backend restart and accepts smaller new-instance sequences', async () => {
  const view = render(<Shell />); await ready()
  feed.publish(operation('global', 'succeeded', '2099-09-30T02:00:00Z', true), operation('newer', 'failed', '2099-09-30T03:00:00Z'))
  await poll()
  const before = src('alpha'), other = src('beta')
  feed.restart(); await poll()
  await waitFor(() => expect(src('alpha')).not.toBe(before))
  expect(src('beta')).not.toBe(other)
  const reset = src('alpha')
  feed.publish(operation('after-restart', 'succeeded', '2026-09-30T01:00:00Z'))
  await poll()
  await waitFor(() => expect(src('alpha')).not.toBe(reset))
  view.unmount(); client.clear()
  render(<Shell />); await ready()
  await waitFor(() => expect(src('alpha')).not.toBe(reset))
})
