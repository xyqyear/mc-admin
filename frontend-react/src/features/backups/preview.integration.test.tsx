import { act, fireEvent, render, renderHook, screen, waitFor } from '@testing-library/react'
import { afterAll, afterEach, beforeAll, beforeEach, expect, it, vi } from 'vitest'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { createTestClient, deferred } from '@/test/http'
import { createOperationFeed } from '@/test/operations'
import { queryKeys } from '@/shared/http/api'
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

it('discovers preview acceptance after its submitting view has unmounted', async () => {
  const feed = createOperationFeed()
  const submitted = deferred<void>(), release = deferred<void>()
  let reads = 0
  server.use(feed.handler,
    http.post('*/api/snapshots/previews', async () => {
      submitted.resolve(); await release.promise
      feed.publish({ operation_id: 'preview', kind: 'snapshot_preview', state: 'queued', data_changed: false, updated_at: '2026-10-07T00:00:00Z', ended_at: null, resources: [] })
      feed.setActiveCount(1)
      return HttpResponse.json({ task_id: 'preview' }, { status: 202 })
    }),
    http.get('*/api/tasks/preview', () => { reads++; return HttpResponse.json({ task_id: 'preview', status: 'running' }) }),
  )
  render(<TestProviders client={client}><OperationObserver sessionId="owner" /></TestProviders>)
  await waitFor(() => expect(client.getQueryData(queryKeys.operations.session('owner'))).toBeTruthy())
  const view = renderHook(() => useSnapshotPreview(request), { wrapper })
  await submitted.promise
  view.unmount()
  await act(async () => { release.resolve() })
  await waitFor(() => expect(client.getQueryData(queryKeys.operations.checkpoint('owner'))).toEqual({ cursor: '1:1', active_count: 1 }))
  expect(reads).toBe(0)
})

it('keeps accepted preparation active through progress and disconnection without cancelling on unmount', async () => {
  let cancellations = 0
  let reads = 0
  server.use(
    http.post('*/api/snapshots/previews', () => HttpResponse.json({ task_id: 'preview' }, { status: 202 })),
    http.get('*/api/tasks/preview', () => {
      reads++
      return reads === 1 ? HttpResponse.json({ task_id: 'preview', status: 'running', progress: 100, message: '正在收尾' }) : HttpResponse.error()
    }),
    http.post('*/api/tasks/preview/cancel', () => { cancellations++; return HttpResponse.json({}) }),
  )
  const view = renderHook(() => useSnapshotPreview(request), { wrapper })
  await waitFor(() => expect(view.result.current.message).toBe('正在收尾'))
  expect(view.result.current.result).toBeNull()
  expect(view.result.current.active).toBe(true)
  await waitFor(() => expect(reads).toBeGreaterThan(1), { timeout: 3000 })
  expect(view.result.current.active).toBe(true)
  expect(view.result.current.error).toBeNull()
  view.unmount()
  expect(cancellations).toBe(0)
})

it('waits for the cancelled terminal task before ending preparation', async () => {
  let cancelAccepted = false
  let cancelled = false
  server.use(
    http.post('*/api/snapshots/previews', () => HttpResponse.json({ task_id: 'preview' }, { status: 202 })),
    http.get('*/api/tasks/preview', () => HttpResponse.json({ task_id: 'preview', status: cancelled ? 'cancelled' : 'running', message: cancelled ? '预览准备已停止' : cancelAccepted ? '正在停止预览准备' : '正在准备' })),
    http.post('*/api/tasks/preview/cancel', () => { cancelAccepted = true; return HttpResponse.json({}) }),
  )
  const view = renderHook(() => useSnapshotPreview(request), { wrapper })
  await waitFor(() => expect(view.result.current.taskId).toBe('preview'))
  await act(async () => { await view.result.current.cancel() })
  await waitFor(() => expect(view.result.current.message).toBe('正在停止预览准备'), { timeout: 3000 })
  expect(view.result.current.active).toBe(true)
  expect(view.result.current.error).toBeNull()
  expect(view.result.current.result).toBeNull()
  cancelled = true
  await waitFor(() => expect(view.result.current.active).toBe(false), { timeout: 3000 })
  expect(view.result.current.error).toBe('预览准备已停止')
  expect(view.result.current.result).toBeNull()
})

it('pages file changes and applies the same preview identity before releasing it on close', async () => {
  const applied = vi.fn()
  let released = false
  server.use(
    http.post('*/api/snapshots/previews', () => HttpResponse.json({ task_id: 'preview' }, { status: 202 })),
    http.get('*/api/tasks/preview', () => HttpResponse.json({
      task_id: 'preview', status: 'completed', result: {
        preview_id: 'ready', kind: 'files', preview_summary: '3 个文件更新',
        skipped_count: 1, notice: '预览后在线文件仍可能变化',
      },
    })),
    http.get('*/api/snapshots/previews/ready/actions', ({ request }) => {
      const cursor = new URL(request.url).searchParams.get('cursor')
      return HttpResponse.json(cursor === '0'
        ? { actions: [{ action: 'updated', item: 'plugins/first.yml' }], next_cursor: 123 }
        : { actions: [{ action: 'deleted', item: 'plugins/last.yml' }], next_cursor: null })
    }),
    http.delete('*/api/snapshots/previews/ready', () => {
      released = true
      return HttpResponse.json({ task_id: 'cleanup' }, { status: 202 })
    }),
    http.get('*/api/tasks/cleanup', () => HttpResponse.json({ task_id: 'cleanup', status: 'completed', result: {} })),
  )
  const view = render(<SnapshotPreviewDialog request={request} onClose={() => {}} onRestore={applied} />, { wrapper })
  await screen.findByText('plugins/first.yml')
  expect(screen.getByText('所选范围包含忽略目录，这些内容将保持不变。')).toBeTruthy()
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
