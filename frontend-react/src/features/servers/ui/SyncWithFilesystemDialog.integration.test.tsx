import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterAll, afterEach, beforeAll, expect, it, vi } from 'vitest'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { createTaskEvents, taskResponse } from '@/test/taskEvents'
import { createTestClient } from '@/test/http'
import { TestProviders } from '@/test/TestProviders'
import SyncWithFilesystemDialog from './SyncWithFilesystemDialog'

const server = setupServer()
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterAll(() => server.close())
afterEach(() => server.resetHandlers())

it('keeps partial synchronization errors visible and prevents accidental reapplication', async () => {
  const client = createTestClient()
  const feed = createTaskEvents()
  let applied = 0
  const onClose = vi.fn()
  server.use(feed.handler,
    http.get('*/api/tasks', () => HttpResponse.json({ tasks: [] })),
    http.post('*/api/servers/sync', async ({ request }) => {
      const input = await request.json() as { dry_run: boolean }
      if (!input.dry_run) applied++
      const taskId = input.dry_run ? 'sync-preview' : 'sync-apply'
      feed.upsert(taskResponse(taskId, { task_type: 'server_sync', status: 'completed', result: {
        applied: !input.dry_run, adopted: [], removed: [],
        preview: input.dry_run ? [{ server_id: 'alpha', action: 'adopt', game_port: 25565, rcon_port: 25575 }] : [],
        errors: input.dry_run ? [] : [{ server_id: 'alpha', stage: 'adopt', error: '服务器目录暂时无法读取' }],
      } }))
      return HttpResponse.json({ task_id: taskId }, { status: 202 })
    }),
  )
  const view = render(<TestProviders client={client}><SyncWithFilesystemDialog open onClose={onClose} /></TestProviders>)
  await screen.findByText('alpha')
  fireEvent.click(screen.getByRole('button', { name: '应用同步' }))
  await screen.findByText('服务器目录暂时无法读取')
  expect(onClose).not.toHaveBeenCalled()
  expect(screen.queryByRole('button', { name: '应用同步' })).toBeNull()
  expect(screen.getByRole('button', { name: '查看任务' })).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: /^关闭$/ }))
  await waitFor(() => expect(onClose).toHaveBeenCalledOnce())
  expect(applied).toBe(1)
  view.unmount()
  client.clear()
})
