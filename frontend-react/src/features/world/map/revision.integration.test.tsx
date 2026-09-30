import L from 'leaflet'
import { act, render, screen, waitFor } from '@testing-library/react'
import { afterAll, afterEach, beforeAll, beforeEach, expect, it } from 'vitest'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { createTestClient } from '@/test/http'
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
let operations: Operation[]
beforeEach(() => {
  client = createTestClient()
  operations = []
  server.use(http.get('*/api/operations', () => HttpResponse.json(operations)))
})
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
  return { operation_id: id, kind: 'snapshot_restore', legacy_id: id, state, data_changed: state !== 'running', failure_code: null,
    updated_at: time, ended_at: state === 'running' ? null : time,
    resources: [{ kind: 'files', server_id: global ? null : 'alpha', generation: global ? null : 1, path: '' }] }
}
async function poll() { await act(async () => { await client.refetchQueries({ queryKey: queryKeys.operations.all }) }) }

it.each(['succeeded', 'failed', 'cancelled'])('refreshes same-mtime tiles after an unmounted restore becomes %s, without changing other servers', async state => {
  operations = [operation('restore', 'running', '2026-09-30T01:00:00Z')]
  const view = render(<Shell />)
  await poll()
  const before = src('alpha'), other = src('beta')
  client.setQueryData(queryKeys.snapshots.history('alpha'), { total: 0, restorations: [] })
  view.rerender(<Shell visible={false} />)
  operations = [operation('restore', state, '2026-09-30T01:01:00Z')]
  await poll()
  expect(client.getQueryState(queryKeys.snapshots.history('alpha'))?.isInvalidated).toBe(true)
  view.rerender(<Shell />)
  await waitFor(() => expect(src('alpha')).not.toBe(before))
  expect(new URL(src('alpha')).searchParams.get('mt')).toBe('100')
  expect(src('beta')).toBe(other)
  const restored = src('alpha')
  operations.unshift({ ...operation('preview', 'succeeded', '2026-09-30T01:02:00Z'), kind: 'snapshot_preview', data_changed: false })
  await poll()
  expect(src('alpha')).toBe(restored)
})

it('keeps the newest global or server revision across old history replay and a browser reload', async () => {
  operations = [operation('global', 'succeeded', '2026-09-30T02:00:00Z', true), operation('old', 'succeeded', '2026-09-30T01:00:00Z')]
  let view = render(<Shell />)
  await poll()
  await waitFor(() => expect(new URL(src('alpha')).searchParams.get('revision')).toContain('global'))
  expect(new URL(src('beta')).searchParams.get('revision')).toContain('global')
  const before = src('alpha')
  operations.push(operation('older', 'failed', '2026-09-29T01:00:00Z'))
  await poll()
  expect(src('alpha')).toBe(before)
  view.unmount(); client.clear()
  view = render(<Shell />)
  await poll()
  await waitFor(() => expect(src('alpha')).toBe(before))
  view.unmount()
})
