import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterAll, afterEach, beforeAll, beforeEach, expect, it, vi } from 'vitest'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { createTestClient, deferred } from '@/test/http'
import { TestProviders } from '@/test/TestProviders'
import { SnapshotRecoveryContext } from '../snapshotRecoveryContext'
import { FileBatchActions } from './FileBatchActions'

const server = setupServer()
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterAll(() => server.close())
let client: ReturnType<typeof createTestClient>
beforeEach(() => { client = createTestClient() })
afterEach(() => { client.clear(); server.resetHandlers() })

it('keeps packing blocked between acceptance and the first confirmed task observation', async () => {
  const observed = deferred<void>()
  let requests = 0
  let taskReads = 0
  server.use(
    http.post('*/api/snapshots/targets/check', () => HttpResponse.json({ allowed: true, skipped_count: 0 })),
    http.post('*/api/archive/compress', async ({ request }) => {
      requests++
      expect(await request.json()).toEqual({ server_id: 'alpha', paths: ['/config/a.txt', '/plugins'] })
      return HttpResponse.json({ task_id: 'pack' }, { status: 202 })
    }),
    http.get('*/api/tasks/pack', async () => { taskReads++; await observed.promise; return HttpResponse.json({ task_id: 'pack', status: 'completed', result: { filename: 'selection.7z' } }) }),
  )
  render(<TestProviders client={client}><SnapshotRecoveryContext.Provider value={{ busy: false, create: vi.fn(), restore: vi.fn(), history: vi.fn() }}><FileBatchActions serverId="alpha" paths={['/config/a.txt', '/plugins']} basePath="/" /></SnapshotRecoveryContext.Provider></TestProviders>)
  const trigger = screen.getByRole('button', { name: '打包所选' }) as HTMLButtonElement
  fireEvent.click(trigger)
  fireEvent.click(screen.getByRole('button', { name: '开始压缩' }))
  await waitFor(() => expect(taskReads).toBeGreaterThan(0))
  expect((screen.getByRole('button', { name: '压缩中...' }) as HTMLButtonElement).disabled).toBe(true)
  expect(trigger.disabled).toBe(true)
  fireEvent.click(screen.getByRole('button', { name: '压缩中...' }))
  expect(requests).toBe(1)
  observed.resolve()
  const completed = await screen.findByRole('dialog', { name: '压缩完成' })
  expect(within(completed).getByText('selection.7z')).toBeTruthy()
})
