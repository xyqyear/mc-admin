import { act, fireEvent, render, renderHook, screen, waitFor } from '@testing-library/react'
import { afterAll, afterEach, beforeAll, beforeEach, expect, it, vi } from 'vitest'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { createTaskEvents, taskResponse } from '@/test/taskEvents'
import { createTestClient, deferred } from '@/test/http'
import { queryKeys } from '@/shared/http/api'
import { taskQueryKeys } from '@/features/tasks/queries'
import { OperationObserver } from '@/app/operations/OperationObserver'
import { TestProviders } from '@/test/TestProviders'
import { useSnapshotPreview } from './commands'
import type { SnapshotPreviewRequest } from './contracts'
import { SnapshotPreviewDialog } from './ui/SnapshotPreviewDialog'

const server = setupServer()
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterAll(() => server.close())
let client: ReturnType<typeof createTestClient>
beforeEach(() => { client = createTestClient() })
afterEach(() => { client.clear(); server.resetHandlers(); vi.restoreAllMocks() })
const wrapper = ({ children }: { children: React.ReactNode }) => <TestProviders client={client}>{children}</TestProviders>
const request: SnapshotPreviewRequest = { source_snapshot_id: 'source', scope: { kind: 'paths', server_id: 'alpha', paths: ['plugins'] } }
const running = taskResponse('preview', { task_type: 'snapshot_preview', progress: 100, message: '正在收尾' })

it('discovers preview acceptance after its submitting view has unmounted', async () => {
  const feed = createTaskEvents()
  const submitted = deferred<void>(), release = deferred<void>()
  let reads = 0
  server.use(feed.handler,
    http.post('*/api/snapshots/previews', async () => {
      submitted.resolve(); await release.promise
      feed.upsert(running)
      feed.operations({ items: [{ sequence: 1, operation_id: 'preview', kind: 'snapshot_preview', state: 'queued', data_changed: false,
        updated_at: '2026-10-07T00:00:00Z', ended_at: null, resources: [] }], next_cursor: 'accepted', active_count: 1, has_more: false, reset_required: false })
      return HttpResponse.json({ task_id: 'preview' }, { status: 202 })
    }),
    http.get('*/api/tasks/preview', () => { reads++; return HttpResponse.json(running) }),
  )
  render(<TestProviders client={client}><OperationObserver sessionId="owner" /></TestProviders>)
  await waitFor(() => expect(feed.activeConnections).toBe(1))
  const view = renderHook(() => useSnapshotPreview(request), { wrapper })
  await submitted.promise
  view.unmount()
  await act(async () => { release.resolve() })
  await waitFor(() => expect(client.getQueryData(queryKeys.operations.checkpoint('owner'))).toEqual({ cursor: 'accepted', active_count: 1 }))
  expect(client.getQueryData(taskQueryKeys.events())).toMatchObject({ tasks: [expect.objectContaining({ taskId: 'preview', status: 'running' })] })
  expect(reads).toBe(0)
  expect(feed.connections).toBe(1)
})

it('keeps accepted preparation active at 100 percent and through disconnection without cancelling on unmount', async () => {
  const feed = createTaskEvents()
  let cancellations = 0
  server.use(feed.handler,
    http.post('*/api/snapshots/previews', () => { feed.upsert(running); return HttpResponse.json({ task_id: 'preview' }, { status: 202 }) }),
    http.get('*/api/tasks/preview', () => HttpResponse.json(running)),
    http.post('*/api/tasks/preview/cancel', () => { cancellations++; return HttpResponse.json({}) }),
  )
  const view = renderHook(() => useSnapshotPreview(request), { wrapper })
  await waitFor(() => expect(view.result.current.message).toBe('正在收尾'))
  expect(view.result.current.result).toBeNull()
  expect(view.result.current.active).toBe(true)
  act(() => feed.close())
  await waitFor(() => expect(client.getQueryData(taskQueryKeys.events())).toMatchObject({ connected: false }))
  expect(view.result.current.active).toBe(true)
  expect(view.result.current.error).toBeNull()
  view.unmount()
  expect(cancellations).toBe(0)
})

it('waits for the cancelled terminal event before ending preparation', async () => {
  const feed = createTaskEvents()
  let cancelAccepted = false
  server.use(feed.handler,
    http.post('*/api/snapshots/previews', () => { feed.upsert(running); return HttpResponse.json({ task_id: 'preview' }, { status: 202 }) }),
    http.get('*/api/tasks/preview', () => HttpResponse.json(running)),
    http.post('*/api/tasks/preview/cancel', () => {
      cancelAccepted = true
      feed.upsert({ ...running, message: '正在停止预览准备' })
      return HttpResponse.json({})
    }),
  )
  const view = renderHook(() => useSnapshotPreview(request), { wrapper })
  await waitFor(() => expect(view.result.current.taskId).toBe('preview'))
  await act(async () => { await view.result.current.cancel() })
  await waitFor(() => expect(view.result.current.message).toBe('正在停止预览准备'))
  expect(cancelAccepted).toBe(true)
  expect(view.result.current.active).toBe(true)
  expect(view.result.current.error).toBeNull()
  expect(view.result.current.result).toBeNull()
  act(() => feed.upsert({ ...running, status: 'cancelled', message: '预览准备已停止' }))
  await waitFor(() => expect(view.result.current.active).toBe(false))
  expect(view.result.current.error).toBe('预览准备已停止')
  expect(view.result.current.result).toBeNull()
})

it('pages file changes and applies the same preview identity before releasing it on close', async () => {
  const feed = createTaskEvents()
  const applied = vi.fn()
  let released = false
  const ready = taskResponse('preview', { task_type: 'snapshot_preview', status: 'completed', result: {
    preview_id: 'ready', kind: 'files', preview_summary: '3 个文件更新',
    skipped_count: 1, skipped_paths: ['plugins/private'], notice: '预览后在线文件仍可能变化',
  } })
  const cleanup = taskResponse('cleanup', { task_type: 'snapshot_preview_cleanup', status: 'completed', result: {} })
  server.use(feed.handler,
    http.post('*/api/snapshots/previews', () => { feed.upsert(ready); return HttpResponse.json({ task_id: 'preview' }, { status: 202 }) }),
    http.get('*/api/tasks/preview', () => HttpResponse.json(ready)),
    http.get('*/api/snapshots/previews/ready/actions', ({ request }) => {
      const cursor = new URL(request.url).searchParams.get('cursor')
      return HttpResponse.json(cursor === '0'
        ? { actions: [{ action: 'updated', item: 'plugins/first.yml' }], next_cursor: 123 }
        : { actions: [{ action: 'deleted', item: 'plugins/last.yml' }], next_cursor: null })
    }),
    http.delete('*/api/snapshots/previews/ready', () => {
      released = true
      feed.upsert(cleanup)
      return HttpResponse.json({ task_id: 'cleanup' }, { status: 202 })
    }),
    http.get('*/api/tasks/cleanup', () => HttpResponse.json(cleanup)),
  )
  const view = render(<SnapshotPreviewDialog request={request} onClose={() => {}} onRestore={applied} />, { wrapper })
  await screen.findByText('plugins/first.yml')
  expect(screen.getByText('将跳过 1 个忽略路径，保留其当前内容。')).toBeTruthy()
  expect(screen.getByText('plugins/private')).toBeTruthy()
  expect(screen.getByRole('button', { name: '上一页' }).hasAttribute('disabled')).toBe(true)
  fireEvent.click(screen.getByRole('button', { name: '下一页' }))
  await screen.findByText('plugins/last.yml')
  expect(screen.queryByText('plugins/first.yml')).toBeNull()
  expect(screen.getByRole('button', { name: '下一页' }).hasAttribute('disabled')).toBe(true)
  fireEvent.click(screen.getByRole('button', { name: '上一页' }))
  await screen.findByText('plugins/first.yml')
  fireEvent.click(screen.getByRole('button', { name: '按此预览恢复' }))
  expect(applied).toHaveBeenCalledExactlyOnceWith('ready')
  expect(released).toBe(false)
  view.rerender(<SnapshotPreviewDialog request={null} onClose={() => {}} />)
  await waitFor(() => expect(released).toBe(true))
})
