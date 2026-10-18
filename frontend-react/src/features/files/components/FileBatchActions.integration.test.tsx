import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterAll, afterEach, beforeAll, beforeEach, expect, it, vi } from 'vitest'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { taskEventsUnavailable, createTaskEvents, taskResponse } from '@/test/taskEvents'
import { createTestClient, deferred } from '@/test/http'
import { TestProviders } from '@/test/TestProviders'
import { SnapshotRecoveryContext } from '../snapshotRecoveryContext'
import { FileBatchActions } from './FileBatchActions'
import { queryKeys } from '@/shared/http/api'

const server = setupServer(taskEventsUnavailable)
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

it('shows streamed deletion counters after confirmation and retains captured paths and partial results', async () => {
  client.setQueryData(queryKeys.serverInfos.detail('alpha'), { id: 'alpha', serverGeneration: 1 })
  const feed = createTaskEvents()
  const writes: unknown[] = []
  let cancellations = 0
  let reads = 0
  const task = taskResponse('batch-delete', { task_type: 'file_delete', progress: 100,
    progress_details: { kind: 'items', processed: 1, total: 2, deleted: 1, failed: 0, pending: 1 } })
  server.use(feed.handler,
    http.get('*/api/snapshots/targets/rules', () => HttpResponse.json({ server_id: 'alpha', server_generation: 1, ignored_paths: [], rules_version: 'v1' })),
    http.post('*/api/servers/alpha/files/delete-batch', async ({ request }) => {
      writes.push(await request.json())
      feed.upsert(task)
      return HttpResponse.json({ task_id: task.task_id }, { status: 202 })
    }),
    http.get('*/api/tasks/batch-delete', () => { reads++; return HttpResponse.json(task) }),
    http.post('*/api/tasks/batch-delete/cancel', () => { cancellations++; return HttpResponse.json({}) }),
  )
  const deleted = vi.fn()
  const controls = (paths: string[]) => <TestProviders client={client}><SnapshotRecoveryContext.Provider value={{ busy: false, create: vi.fn(), restore: vi.fn(), history: vi.fn() }}><FileBatchActions serverId="alpha" paths={paths} basePath="/" onDeleted={deleted} /></SnapshotRecoveryContext.Provider></TestProviders>
  const view = render(controls(['/a.txt', '/locked']))
  fireEvent.click(screen.getByRole('button', { name: /^批量删除$/ }))
  const confirmation = await screen.findByRole('alertdialog', { name: '确认批量删除' })
  fireEvent.click(within(confirmation).getByRole('button', { name: /^删除$/ }))
  await waitFor(() => expect(screen.queryByRole('alertdialog')).toBeNull())
  await screen.findByText('已处理 1/2 项，已删除 1 项，失败 0 项，待处理 1 项')
  const initialReads = reads
  expect((screen.getByRole('button', { name: /^批量删除$/ }) as HTMLButtonElement).disabled).toBe(true)
  view.rerender(controls(['/different-selection']))
  expect((screen.getByRole('button', { name: /^批量删除$/ }) as HTMLButtonElement).disabled).toBe(true)
  expect(writes).toEqual([{ paths: ['/a.txt', '/locked'] }])
  expect(deleted).not.toHaveBeenCalled()
  expect(cancellations).toBe(0)
  const outcome = { paths: ['/a.txt', '/locked'], results: [{ path: 'a.txt', status: 'deleted' }, { path: 'locked', status: 'failed', message: '权限不足' }], deleted: 1, failed: 1, pending: 0 }
  act(() => feed.upsert({ ...task, status: 'failed', error: '部分条目删除失败', result: outcome }))
  await screen.findByText('locked：权限不足')
  await waitFor(() => expect(deleted).toHaveBeenCalledWith(['/a.txt']))
  expect((screen.getByRole('button', { name: /^批量删除$/ }) as HTMLButtonElement).disabled).toBe(false)
  expect(reads).toBe(initialReads)
  expect(cancellations).toBe(0)
})
