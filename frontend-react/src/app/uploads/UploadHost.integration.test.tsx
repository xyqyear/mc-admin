import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterAll, afterEach, beforeAll, beforeEach, expect, it, vi } from 'vitest'
import { Link, Route, Routes } from 'react-router'
import { File as NativeFile } from 'node:buffer'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { createTestClient, deferred } from '@/test/http'
import { TestProviders } from '@/test/TestProviders'
import { taskEventsUnavailable, createTaskEvents, taskResponse } from '@/test/taskEvents'
import { api, queryKeys } from '@/shared/http/api'
import { clearBrowserUploads, clearFinishedUploads, isUploadActive, openArchiveUpload, openFileUpload, useUploadStore } from '@/features/tasks/uploads'
import { useTaskCenterStore } from '@/features/tasks/panelStore'
import UploadTaskList from '@/features/tasks/ui/UploadTaskList'
import { UploadHost } from './UploadHost'

const server = setupServer(taskEventsUnavailable)
let client: ReturnType<typeof createTestClient>
const originalAdapter = api.defaults.adapter
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterAll(() => server.close())
beforeEach(() => {
  client = createTestClient()
  clearBrowserUploads()
  useTaskCenterStore.setState({ isOpen: false, modal: false, activeTab: 'background' })
})
afterEach(() => { cleanup(); clearBrowserUploads(); client.clear(); server.resetHandlers(); vi.restoreAllMocks(); api.defaults.adapter = originalAdapter })

function showHost() {
  return render(<TestProviders client={client}>
    <button data-task-center-launcher>任务中心</button>
    <Link to="/other">切换页面</Link>
    <Routes><Route path="/" element={<p>原文件页</p>} /><Route path="/other" element={<p>其他服务器</p>} /></Routes>
    <UploadHost /><UploadTaskList />
  </TestProviders>)
}

it('keeps simultaneous uploads in different servers independent', async () => {
  const pending = deferred<void>()
  const destinations: string[] = []
  server.use(
    http.post('*/api/servers/:id/files/upload/check', ({ params }) => HttpResponse.json({ session_id: params.id, conflicts: [] })),
    http.post('*/api/servers/:id/files/upload/policy', () => HttpResponse.json({ message: 'ok' })),
    http.post('*/api/servers/:id/files/upload/multiple', async ({ request, params }) => {
      destinations.push(`${params.id}:${new URL(request.url).searchParams.get('path')}`)
      await pending.promise
      return HttpResponse.json({ results: { 'same.txt': { status: 'success' } } })
    }),
  )
  showHost()
  act(() => openFileUpload('alpha', '/one', [new File(['first'], 'same.txt')]))
  fireEvent.click(await screen.findByRole('button', { name: '检查冲突并上传' }))
  await waitFor(() => expect(destinations).toEqual(['alpha:/one']))
  fireEvent.click(screen.getByRole('button', { name: '收起上传窗口' }))
  await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
  act(() => openFileUpload('beta', '/two', [new File(['second'], 'same.txt')]))
  fireEvent.click(await screen.findByRole('button', { name: '检查冲突并上传' }))
  await waitFor(() => expect(destinations).toEqual(['alpha:/one', 'beta:/two']))
  expect(useUploadStore.getState().tasks.filter(isUploadActive)).toHaveLength(2)
  await act(async () => pending.resolve())
  await waitFor(() => expect(useUploadStore.getState().tasks.map(task => task.status)).toEqual(['complete', 'complete']))
})

it('keeps original destination and transfer across hiding and navigation, then reopens the retained result without resubmitting', async () => {
  const started = deferred<AbortSignal>()
  const finish = deferred<void>()
  let submissions = 0
  server.use(
    http.post('*/api/servers/alpha/files/upload/check', () => HttpResponse.json({ session_id: 'upload', conflicts: [] })),
    http.post('*/api/servers/alpha/files/upload/policy', () => HttpResponse.json({ message: 'ok' })),
    http.post('*/api/servers/alpha/files/upload/multiple', async ({ request }) => {
      submissions++
      expect(new URL(request.url).searchParams.get('path')).toBe('/original')
      started.resolve(request.signal)
      await finish.promise
      return HttpResponse.json({ results: { 'file.txt': { status: 'success' } } })
    }),
  )
  client.setQueryData(queryKeys.files.list('alpha', '/original'), { items: [] })
  showHost()
  act(() => openFileUpload('alpha', '/original', [new File(['real bytes'], 'file.txt')]))
  fireEvent.click(await screen.findByRole('button', { name: '检查冲突并上传' }))
  const signal = await started.promise
  fireEvent.click(screen.getByRole('button', { name: '收起上传窗口' }))
  await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
  fireEvent.click(screen.getByRole('link', { name: '切换页面' }))
  expect(screen.getByText('其他服务器')).toBeTruthy()
  expect(signal.aborted).toBe(false)
  expect(useTaskCenterStore.getState().activeTab).toBe('upload')
  fireEvent.click(screen.getByRole('button', { name: '查看上传：file.txt' }))
  expect(await screen.findByRole('dialog')).toBeTruthy()
  expect(submissions).toBe(1)
  fireEvent.click(screen.getByRole('button', { name: '收起上传窗口' }))
  await act(async () => finish.resolve())
  await waitFor(() => expect(useUploadStore.getState().tasks[0].status).toBe('complete'))
  expect(client.getQueryState(queryKeys.files.list('alpha', '/original'))?.isInvalidated).toBe(true)
  fireEvent.click(screen.getByRole('button', { name: '查看上传：file.txt' }))
  expect(await screen.findByText('上传完成！')).toBeTruthy()
  expect(screen.getByText('成功')).toBeTruthy()
  expect(submissions).toBe(1)
  fireEvent.click(screen.getByRole('button', { name: '关闭' }))
  await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
  fireEvent.click(screen.getByRole('button', { name: '清除已结束' }))
  expect(useUploadStore.getState().tasks).toEqual([])
})

it('retains pending per-file overwrite choices when hidden and reports mixed results without claiming full success', async () => {
  let policy: unknown
  server.use(
    http.post('*/api/servers/alpha/files/upload/check', () => HttpResponse.json({ session_id: 'conflict', conflicts: [{ path: 'same.txt', type: 'file' }] })),
    http.post('*/api/servers/alpha/files/upload/policy', async ({ request }) => { policy = await request.json(); return HttpResponse.json({ message: 'ok' }) }),
    http.post('*/api/servers/alpha/files/upload/multiple', () => HttpResponse.json({ results: { 'same.txt': { status: 'skipped', reason: 'exists' }, 'other.txt': { status: 'failed', reason: '拒绝写入' } } })),
  )
  showHost()
  act(() => openFileUpload('alpha', '/', [new File(['keep'], 'same.txt'), new File(['new'], 'other.txt')]))
  fireEvent.click(await screen.findByRole('button', { name: '检查冲突并上传' }))
  fireEvent.click(await screen.findByRole('radio', { name: '为每个文件单独选择' }))
  fireEvent.click(screen.getByRole('checkbox'))
  fireEvent.click(screen.getByRole('button', { name: '收起上传窗口' }))
  await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
  expect(policy).toBeUndefined()
  act(() => clearFinishedUploads())
  expect(useUploadStore.getState().tasks).toHaveLength(1)
  fireEvent.click(screen.getByRole('button', { name: '查看上传：same.txt' }))
  expect((await screen.findByRole('checkbox')).getAttribute('aria-checked')).toBe('false')
  fireEvent.click(screen.getByRole('button', { name: '开始上传' }))
  await screen.findByText('部分文件上传失败')
  expect(policy).toEqual({ mode: 'per_file', decisions: [{ path: 'same.txt', overwrite: false }] })
  expect(useUploadStore.getState().tasks[0].status).toBe('error')
})

it('cancels transfer only through the explicit action and releases records and requests when the authenticated host leaves', async () => {
  const requests: AbortSignal[] = []
  const abort = vi.spyOn(XMLHttpRequest.prototype, 'abort')
  const pending = deferred<void>()
  server.use(
    http.post('*/api/servers/alpha/files/upload/check', () => HttpResponse.json({ session_id: 'session', conflicts: [] })),
    http.post('*/api/servers/alpha/files/upload/policy', () => HttpResponse.json({ message: 'ok' })),
    http.post('*/api/servers/alpha/files/upload/multiple', async ({ request }) => { requests.push(request.signal); await pending.promise; return HttpResponse.json({ results: {} }) }),
  )
  const view = showHost()
  act(() => openFileUpload('alpha', '/', [new File(['a'], 'cancel.txt')]))
  fireEvent.click(await screen.findByRole('button', { name: '检查冲突并上传' }))
  await waitFor(() => expect(requests).toHaveLength(1))
  fireEvent.click(screen.getByRole('button', { name: '取消上传' }))
  await waitFor(() => expect(useUploadStore.getState().tasks[0].status).toBe('cancelled'))
  expect(abort).toHaveBeenCalledTimes(1)
  fireEvent.click(screen.getByRole('button', { name: '检查冲突并上传' }))
  await waitFor(() => expect(requests).toHaveLength(2))
  view.unmount()
  expect(abort).toHaveBeenCalledTimes(2)
  expect(useUploadStore.getState().tasks).toEqual([])
  await act(async () => pending.resolve())
})

it('keeps archive verification alive while hidden and waits for the actual publication result', async () => {
  api.defaults.adapter = 'http'
  const digest = 'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad'
  const feed = createTaskEvents()
  const hash = taskResponse('hash', { task_type: 'archive_hash', progress: 100 })
  const publication = taskResponse('publish', { task_type: 'archive_publish', progress: 100 })
  const chunks: string[] = []
  const verifies: unknown[] = []
  let deleted = 0
  server.use(feed.handler,
    http.post('*/api/archive/upload/init', () => HttpResponse.json({ upload_id: 'upload', offset: 0, chunk_size: 8 })),
    http.patch('*/api/archive/upload/upload', async ({ request }) => { chunks.push(await request.text()); return HttpResponse.json({ offset: 3, complete: true }) }),
    http.post('*/api/archive/upload/upload/sha256', () => HttpResponse.json({ task_id: 'hash' })),
    http.get('*/api/tasks/hash', () => HttpResponse.json(hash)),
    http.post('*/api/archive/upload/upload/verify', async ({ request }) => { verifies.push(await request.json()); return HttpResponse.json({ task_id: 'publish' }) }),
    http.get('*/api/tasks/publish', () => HttpResponse.json(publication)),
    http.delete('*/api/archive/upload/upload', () => { deleted++; return new HttpResponse(null, { status: 204 }) }),
  )
  showHost()
  act(() => openArchiveUpload([new NativeFile(['abc'], 'fixture.zip') as File]))
  fireEvent.click(await screen.findByRole('button', { name: '开始上传' }))
  await waitFor(() => expect(useUploadStore.getState().tasks[0].status).toBe('verifying'))
  fireEvent.click(screen.getByRole('button', { name: '收起上传窗口' }))
  await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
  await waitFor(() => expect(feed.activeConnections).toBe(1))
  act(() => feed.upsert({ ...hash, status: 'completed', result: { sha256: digest } }))
  await waitFor(() => expect(verifies).toEqual([{ sha256: digest }]))
  expect(chunks).toEqual(['abc'])
  expect(isUploadActive(useUploadStore.getState().tasks[0])).toBe(true)
  fireEvent.click(screen.getByRole('button', { name: '查看上传：fixture.zip' }))
  expect(await screen.findByRole('dialog', { name: '上传压缩包' })).toBeTruthy()
  expect(within(screen.getByRole('dialog')).getByRole('button', { name: /开始上传/ }).hasAttribute('disabled')).toBe(true)
  act(() => feed.upsert({ ...publication, status: 'completed', result: { path: '/fixture.zip' } }))
  await waitFor(() => expect(useUploadStore.getState().tasks[0].status).toBe('complete'))
  expect(deleted).toBe(0)
})
