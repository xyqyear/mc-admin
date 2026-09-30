import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterAll, afterEach, beforeAll, expect, it } from 'vitest'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { createTestClient } from '@/test/http'
import { TestProviders } from '@/test/TestProviders'
import { taskQueryKeys } from '@/features/tasks/queries'
import { FileSnapshotRecovery } from './FileSnapshotRecovery'

const server = setupServer()
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterAll(() => server.close())
afterEach(() => server.resetHandlers())

it('retains resumed completion until the user closes it, without fetching Restic history', async () => {
  const client = createTestClient()
  let status = 'running'
  server.use(
    http.get('*/api/snapshots/restorations/active', () => HttpResponse.json({ total: status === 'running' ? 1 : 0, restorations: status === 'running' ? [{ id: 'restore', operation_id: 'restore-task', scope: { kind: 'paths', server_id: 'alpha', paths: ['plugins'] }, status }] : [] })),
    http.get('*/api/tasks/restore-task', () => HttpResponse.json({ task_id: 'restore-task', status, message: status === 'running' ? '正在恢复所选文件' : '恢复完成', progress: null })),
  )
  const view = render(<TestProviders client={client}><FileSnapshotRecovery serverId="alpha"><p>文件列表</p></FileSnapshotRecovery></TestProviders>)
  try {
    await screen.findByText('正在恢复所选文件')
    expect(screen.getAllByRole('dialog')).toHaveLength(1)
    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' })
    expect(screen.getByRole('dialog')).toBeTruthy()
    status = 'completed'
    await act(async () => { await client.invalidateQueries({ queryKey: taskQueryKeys.all }) })
    await screen.findByRole('button', { name: '关闭' })
    expect(screen.getAllByRole('dialog')).toHaveLength(1)
    fireEvent.click(screen.getByRole('button', { name: '关闭' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
  } finally { view.unmount(); client.clear() }
})
