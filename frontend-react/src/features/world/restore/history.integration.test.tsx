import { render, screen } from '@testing-library/react'
import { afterAll, afterEach, beforeAll, expect, it } from 'vitest'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { createTestClient } from '@/test/http'
import { TestProviders } from '@/test/TestProviders'
import RestorationHistoryDrawer from '@/features/world/restore/components/RestorationHistoryDrawer'

const server = setupServer()
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterAll(() => server.close())
afterEach(() => server.resetHandlers())
it('keeps old-instance recovery history readable and disables rollback with a reason', async () => {
  const client = createTestClient()
  server.use(http.get('*/api/servers/alpha/world-restore/restorations', () => HttpResponse.json({ total: 1, restorations: [{
    id: 'restoration', server_id: 'alpha', server_generation: 1, binding_issue: 'generation_changed', type: 'world', source_snapshot_id: 'source123', safety_snapshot_id: 'safety123', source_snapshot_exists: true, safety_snapshot_exists: true, selection: { type: 'world' }, status: 'succeeded', started_at: '2026-09-25T00:00:00Z', finished_at: '2026-09-25T01:00:00Z', is_rollback: false,
  }] })))
  const view = render(<TestProviders client={client}><RestorationHistoryDrawer serverId="alpha" open serverStopped onOpenChange={() => {}} /></TestProviders>)
  await screen.findByText('source12')
  expect(screen.getByText('此记录属于同名的旧服务器实例，无法回滚到当前实例。')).toBeTruthy()
  expect((screen.getByRole('button', { name: '回滚' }) as HTMLButtonElement).disabled).toBe(true)
  view.unmount(); client.clear()
})
