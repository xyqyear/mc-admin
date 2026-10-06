// @vitest-environment node
import { JSDOM } from 'jsdom'
import { act, renderHook, waitFor } from '@testing-library/react'
import { afterAll, afterEach, beforeAll, beforeEach, expect, it, vi } from 'vitest'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { createTestClient, deferred } from '@/test/http'
import { TestProviders } from '@/test/TestProviders'

const abcSHA256 = 'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad'
const dom = new JSDOM('', { url: 'http://localhost:3000', pretendToBeVisual: true })
const server = setupServer()
let useArchiveUpload: typeof import('./useArchiveUpload').useArchiveUpload
let queryKeys: typeof import('@/shared/http/api').queryKeys
let taskQueryKeys: typeof import('@/features/tasks/queries').taskQueryKeys
beforeAll(async () => {
  vi.stubGlobal('window', dom.window)
  vi.stubGlobal('document', dom.window.document)
  vi.stubGlobal('requestAnimationFrame', dom.window.requestAnimationFrame.bind(dom.window))
  vi.stubGlobal('cancelAnimationFrame', dom.window.cancelAnimationFrame.bind(dom.window))
  ;({ useArchiveUpload } = await import('./useArchiveUpload'))
  ;({ queryKeys } = await import('@/shared/http/api'))
  ;({ taskQueryKeys } = await import('@/features/tasks/queries'))
  server.listen({ onUnhandledRequest: 'error' })
})
afterAll(() => { server.close(); vi.unstubAllGlobals(); dom.window.close() })
let client: ReturnType<typeof createTestClient>
let chunkBytes: string[]
let verifyBodies: unknown[]
let cleanups: number
let hashReads: number
let publishReads: number
function task(id: string, status: string, result?: unknown) {
  return { task_id: id, task_type: 'archive_upload', name: '上传', status, progress: 100,
    message: status === 'running' ? '发布中' : '已完成', created_at: '2026-10-01T00:00:00Z',
    result, error: status === 'failed' || status === 'cancelled' ? '发布未完成' : null, cancellable: true }
}
beforeEach(() => {
  client = createTestClient(); chunkBytes = []; verifyBodies = []; cleanups = 0; hashReads = 0; publishReads = 0
  client.setQueryData(queryKeys.archive.files('/'), { items: [], current_path: '/' })
  server.use(
    http.post('*/api/archive/upload/init', () => HttpResponse.json({ upload_id: 'upload', offset: 0, chunk_size: 2 })),
    http.patch('*/api/archive/upload/upload', async ({ request }) => {
      const content = await request.text()
      chunkBytes.push(content)
      const offset = Number(request.headers.get('upload-offset')) + content.length
      return HttpResponse.json({ offset, complete: offset === 3 })
    }),
    http.post('*/api/archive/upload/upload/sha256', () => HttpResponse.json({ task_id: 'hash' })),
    http.get('*/api/tasks/hash', () => { hashReads++; return HttpResponse.json(task('hash', 'completed', { sha256: abcSHA256 })) }),
    http.post('*/api/archive/upload/upload/verify', async ({ request }) => {
      verifyBodies.push(await request.json()); return HttpResponse.json({ task_id: 'publish' })
    }),
    http.get('*/api/tasks/publish', () => { publishReads++; return HttpResponse.json(task('publish', 'completed', { path: '/fixture.zip' })) }),
    http.delete('*/api/archive/upload/upload', () => { cleanups++; return new HttpResponse(null, { status: 204 }) }),
  )
})
afterEach(() => { client.clear(); server.resetHandlers() })
function showUpload(content = 'abc') {
  const files = [new File([new TextEncoder().encode(content)], 'fixture.zip')]
  const view = renderHook(() => useArchiveUpload(true, files), {
    wrapper: ({ children }) => <TestProviders client={client}>{children}</TestProviders>,
  })
  act(() => view.result.current.start())
  return view
}

it('hashes actual abc bytes and waits through a disconnect and running 100% before publishing', async () => {
  const terminal = deferred<void>()
  server.use(http.get('*/api/tasks/publish', async () => {
    publishReads++
    if (publishReads === 1) return HttpResponse.json({ detail: '暂时不可用' }, { status: 503 })
    if (publishReads === 2) return HttpResponse.json(task('publish', 'running'))
    await terminal.promise
    return HttpResponse.json(task('publish', 'completed', { path: '/fixture.zip' }))
  }))
  const { result } = showUpload()
  await waitFor(() => expect(publishReads).toBeGreaterThanOrEqual(2), { timeout: 4000 })
  expect(chunkBytes).toEqual(['ab', 'c'])
  expect(verifyBodies).toEqual([{ sha256: abcSHA256 }])
  expect(result.current.phase).toBe('verifying')
  expect(result.current.progress).toBe(100)
  expect(result.current.isWorking).toBe(true)
  expect(client.getQueryState(queryKeys.archive.files('/'))?.isInvalidated).toBe(false)
  await act(async () => terminal.resolve())
  await waitFor(() => expect(result.current.phase).toBe('complete'), { timeout: 4000 })
  expect(result.current.isWorking).toBe(false)
  expect(client.getQueryState(queryKeys.archive.files('/'))?.isInvalidated).toBe(true)
  expect(cleanups).toBe(0)
})

it.each(['abd', 'missing'])('rejects %s integrity without verification or publication and cleans up the session', async content => {
  if (content === 'missing') server.use(http.get('*/api/tasks/hash', () => HttpResponse.json(task('hash', 'completed', {}))))
  const { result } = showUpload(content === 'missing' ? 'abc' : content)
  await waitFor(() => expect(result.current.phase).toBe('error'))
  expect(result.current.detailText).toContain(content === 'missing' ? '缺少 SHA256' : '服务器文件与本地文件不一致')
  await waitFor(() => expect(cleanups).toBe(1))
  expect(verifyBodies).toEqual([])
  expect(publishReads).toBe(0)
  expect(client.getQueryState(queryKeys.archive.files('/'))?.isInvalidated).toBe(false)
})

it.each(['failed', 'cancelled'])('keeps failed publication out of the archive cache (%s)', async status => {
  server.use(http.get('*/api/tasks/publish', () => { publishReads++; return HttpResponse.json(task('publish', status)) }))
  const { result } = showUpload()
  await waitFor(() => expect(result.current.phase).toBe('error'))
  expect(result.current.detailText).toBe('发布未完成')
  expect(verifyBodies).toEqual([{ sha256: abcSHA256 }])
  await waitFor(() => expect(cleanups).toBe(1))
  expect(client.getQueryState(queryKeys.archive.files('/'))?.isInvalidated).toBe(false)
})

it.each(['unmount', 'close'] as const)('stops hash observation on %s and preserves the background input only on unmount', async action => {
  const terminal = deferred<void>()
  server.use(http.get('*/api/tasks/hash', async () => {
    hashReads++; await terminal.promise
    return HttpResponse.json(task('hash', 'completed', { sha256: abcSHA256 }))
  }))
  const view = showUpload()
  await waitFor(() => expect(hashReads).toBe(1))
  client.setQueryData(taskQueryKeys.detail('hash'), { status: 'running' })
  if (action === 'unmount') view.unmount()
  else act(() => view.result.current.close())
  await act(async () => terminal.resolve())
  await waitFor(() => expect(client.getQueryState(taskQueryKeys.detail('hash'))?.isInvalidated).toBe(true))
  if (action === 'close') await waitFor(() => expect(cleanups).toBe(1))
  else expect(cleanups).toBe(0)
  expect(verifyBodies).toEqual([])
  expect(publishReads).toBe(0)
  expect(client.getQueryState(queryKeys.archive.files('/'))?.isInvalidated).toBe(false)
})
