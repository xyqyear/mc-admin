import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterAll, afterEach, beforeAll, beforeEach, expect, it, vi } from 'vitest'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { createTestClient, deferred } from '@/test/http'
import { TestProviders } from '@/test/TestProviders'
import { SnapshotRecoveryContext } from '../snapshotRecoveryContext'
import { FileBatchActions } from './FileBatchActions'
import { queryKeys } from '@/shared/http/api'

const server = setupServer()
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterAll(() => server.close())
let client: ReturnType<typeof createTestClient>
beforeEach(() => { client = createTestClient() })
afterEach(() => { client.clear(); server.resetHandlers(); vi.useRealTimers() })

it('allows mixed snapshot selections and submits original paths while all ignored selections stay disabled', async () => {
  client.setQueryData(queryKeys.serverInfos.detail('alpha'), { id: 'alpha', serverGeneration: 1 })
  let reads = 0
  server.use(http.get('*/api/snapshots/targets/rules', () => {
    reads++
    return HttpResponse.json({ server_id: 'alpha', server_generation: 1, ignored_paths: ['private'], rules_version: 'v1' })
  }))
  const create = vi.fn()
  const restore = vi.fn()
  const controls = (paths: string[]) => <TestProviders client={client}><SnapshotRecoveryContext.Provider value={{ busy: false, create, restore, history: vi.fn() }}><FileBatchActions serverId="alpha" paths={paths} basePath="/" /></SnapshotRecoveryContext.Provider></TestProviders>
  const view = render(controls(['/allowed', '/private']))
  await waitFor(() => expect((screen.getByRole('button', { name: '创建快照' }) as HTMLButtonElement).disabled).toBe(false))
  fireEvent.click(screen.getByRole('button', { name: '创建快照' }))
  fireEvent.click(screen.getByRole('button', { name: '快照恢复' }))
  expect(create).toHaveBeenCalledWith(['/allowed', '/private'], '选中的 2 个条目')
  expect(restore).toHaveBeenCalledWith(['/allowed', '/private'], '选中的 2 个条目')
  view.rerender(controls(['/private/a', '/private/b']))
  expect((screen.getByRole('button', { name: '创建快照' }) as HTMLButtonElement).disabled).toBe(true)
  expect((screen.getByRole('button', { name: '快照恢复' }) as HTMLButtonElement).disabled).toBe(true)
  expect(reads).toBe(1)
})

it('keeps packing blocked between acceptance and the first confirmed task observation', async () => {
  client.setQueryData(queryKeys.serverInfos.detail('alpha'), { id: 'alpha', serverGeneration: 1 })
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(new Date(2026, 9, 7, 15, 42, 3, 123))
  const observed = deferred<void>()
  let requests = 0
  let taskReads = 0
  server.use(
    http.get('*/api/snapshots/targets/rules', () => HttpResponse.json({ server_id: 'alpha', server_generation: 1, ignored_paths: [], rules_version: 'v1' })),
    http.post('*/api/archive/compress', async ({ request }) => {
      requests++
      expect(await request.json()).toEqual({ server_id: 'alpha', paths: ['/config/a.txt', '/plugins'], client_timestamp: '20261007_154203_123' })
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
