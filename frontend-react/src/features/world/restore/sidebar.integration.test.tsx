import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterAll, afterEach, beforeAll, expect, it } from 'vitest'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { createTestClient, deferred } from '@/test/http'
import { TestProviders } from '@/test/TestProviders'
import { useMapStatus } from '@/features/world/queries'
import type { MapStatus } from '@/features/world/map/contracts'
import { WorldRestoreSidebar } from '@/features/world/restore/components/WorldRestoreSidebar'
import WorldRestoreSelectionPanel from '@/features/world/restore/components/WorldRestoreSelectionPanel'

const server = setupServer()
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterAll(() => server.close())
afterEach(() => server.resetHandlers())

function RestoreSidebar() {
  const { data } = useMapStatus('alpha')
  const mapInitialized = !!data?.client_jar_present && !!data.palette_present && !!data.palette_current
  return <WorldRestoreSidebar
    mapInitialized={mapInitialized}
    backup={<WorldRestoreSelectionPanel serverId="alpha" regionDirRelpath="world/region" selection={new Set()} mode="region" serverStopped />}
    players={<p>玩家位置列表</p>}
  />
}

it('retains the open history and rolls back its interrupted row when delayed map status enables tabs', async () => {
  const client = createTestClient()
  const mapStatus = deferred<MapStatus>()
  const rollbacks: string[] = []
  server.use(
    http.get('*/api/servers/alpha/map/status', async () => HttpResponse.json(await mapStatus.promise)),
    http.get('*/api/servers/alpha/world-restore/restorations', () => HttpResponse.json({ total: 1, restorations: [{
      id: 'interrupted-restore', server_id: 'alpha', server_generation: 1, binding_issue: null,
      type: 'world', source_snapshot_id: 'source123456', safety_snapshot_id: 'safety123456',
      source_snapshot_exists: true, safety_snapshot_exists: true, selection: { type: 'world' },
      status: 'interrupted', started_at: '2026-09-25T00:00:00Z', finished_at: '2026-09-25T00:01:00Z',
      is_rollback: false, initiated_by_user_id: 1, error_message: '恢复连接已中断',
    }] })),
    http.post('*/api/servers/alpha/world-restore/restorations/:id/rollback', ({ params }) => {
      rollbacks.push(String(params.id))
      return new HttpResponse(`data: ${JSON.stringify({ event_type: 'complete', restoration_id: 'rollback', message: '安全快照回滚完成' })}\n\n`, { headers: { 'Content-Type': 'text/event-stream' } })
    }),
  )
  const view = render(<TestProviders client={client}><RestoreSidebar /></TestProviders>)
  try {
    fireEvent.click(screen.getByRole('button', { name: '查看恢复历史' }))
    const history = await screen.findByRole('dialog', { name: '恢复历史' })
    await within(history).findByText('source12')
    expect(within(history).getByText('safety12')).toBeTruthy()
    expect(within(history).getByText('已中断')).toBeTruthy()
    expect(screen.queryByRole('tab', { name: '玩家位置', hidden: true })).toBeNull()

    await act(async () => mapStatus.resolve({ client_jar_present: true, palette_present: true, palette_current: true, version: '1.21.11' }))
    await screen.findByRole('tab', { name: '玩家位置', hidden: true })
    expect(screen.getByRole('dialog', { name: '恢复历史' })).toBe(history)
    const rollback = within(history).getByRole('button', { name: '回滚' })
    expect((rollback as HTMLButtonElement).disabled).toBe(false)
    fireEvent.click(rollback)
    fireEvent.click(await screen.findByRole('button', { name: '开始回滚' }))
    await waitFor(() => expect(rollbacks).toEqual(['interrupted-restore']))
    await within(history).findByRole('button', { name: '返回历史' })
    expect(screen.getByRole('dialog', { name: '恢复历史' })).toBe(history)
  } finally {
    mapStatus.resolve({ client_jar_present: true, palette_present: true, palette_current: true, version: '1.21.11' })
    view.unmount()
    client.clear()
  }
})
