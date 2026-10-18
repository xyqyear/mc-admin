import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterAll, afterEach, beforeAll, expect, it } from 'vitest'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { createTaskEvents, taskResponse } from '@/test/taskEvents'
import { createTestClient } from '@/test/http'
import { TestProviders } from '@/test/TestProviders'
import { FileSnapshotRecovery } from './FileSnapshotRecovery'

const server = setupServer()
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterAll(() => server.close())
afterEach(() => server.resetHandlers())

it('retains resumed completion until the user closes it, without fetching Restic history', async () => {
  const client = createTestClient()
  const running = taskResponse('restore-task', { task_type: 'snapshot_restore', message: '正在恢复所选文件' })
  const events = createTaskEvents([running], { activeRestorations: [{ id: 'restore', operation_id: 'restore-task', scope: { kind: 'paths', server_id: 'alpha', paths: ['plugins'] }, status: 'running', targets: [{ server_id: 'alpha', generation: 1 }] }] })
  server.use(events.handler,
    http.get('*/api/servers/alpha', () => HttpResponse.json({ id: 'alpha', name: 'Alpha', server_generation: 1, serverType: 'VANILLA', gameVersion: '1.21', gamePort: 25565, maxMemoryBytes: 1024 ** 3, rconPort: 25575, javaVersion: 21 })),
    http.get('*/api/snapshots/targets/rules', () => HttpResponse.json({ server_id: 'alpha', server_generation: 1, ignored_paths: [], rules_version: 'rules-1' })),
    http.get('*/api/tasks/restore-task', () => HttpResponse.json(running)),
  )
  const view = render(<TestProviders client={client}><FileSnapshotRecovery serverId="alpha"><p>文件列表</p></FileSnapshotRecovery></TestProviders>)
  try {
    await screen.findByText('正在恢复所选文件')
    expect(screen.getAllByRole('dialog')).toHaveLength(1)
    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' })
    expect(screen.getByRole('dialog')).toBeTruthy()
    act(() => {
      events.upsert({ ...running, status: 'completed', message: '恢复完成' })
      events.restorations([])
    })
    await screen.findByRole('button', { name: '关闭' })
    expect(screen.getAllByRole('dialog')).toHaveLength(1)
    fireEvent.click(screen.getByRole('button', { name: '关闭' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
  } finally { view.unmount(); client.clear() }
})
