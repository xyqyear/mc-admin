import { act, renderHook, waitFor } from '@testing-library/react'
import { afterAll, afterEach, beforeAll, beforeEach, expect, it } from 'vitest'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { createTestClient, deferred } from '@/test/http'
import { TestProviders } from '@/test/TestProviders'
import { queryKeys } from '@/shared/http/api'
import { useFileEditor } from '@/features/files/useFileEditor'
import { useMultiFileUpload, FILES_PER_BATCH } from '@/features/files/useMultiFileUpload'
import { fileApi } from '@/features/files/api'
import type { FileItem } from '@/features/files/contracts'

const server = setupServer()
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterAll(() => server.close())
let client: ReturnType<typeof createTestClient>
beforeEach(() => { client = createTestClient() })
afterEach(() => { client.clear(); server.resetHandlers() })
const wrapper = ({ children }: { children: React.ReactNode }) => <TestProviders client={client}>{children}</TestProviders>
const file: FileItem = { name: 'server.properties', path: '/data/server.properties', type: 'file', size: 1, modified_at: 1 }

it('keeps a dirty file draft after a rejected online write and submits intentionally empty content', async () => {
  let remote = 'old'
  let status = 423
  const writes: unknown[] = []
  server.use(
    http.get('*/api/servers/alpha/files/content', () => HttpResponse.json({ content: remote })),
    http.post('*/api/servers/alpha/files/content', async ({ request }) => {
      writes.push(await request.json())
      return status === 200 ? HttpResponse.json({ message: 'ok' }) : HttpResponse.json({ detail: '该文件正在恢复，请稍后重试' }, { status })
    }),
  )
  const { result } = renderHook(() => useFileEditor('alpha'), { wrapper })
  act(() => result.current.handleFileEdit(file))
  await waitFor(() => expect(result.current.editorDraft.ready).toBe(true))
  act(() => result.current.setFileContent('local draft'))
  await act(async () => { await result.current.handleFileSave() })
  expect(result.current.fileContent).toBe('local draft')
  expect(result.current.isEditDialogOpen).toBe(true)
  await waitFor(() => expect(result.current.updateFileMutation.error?.message).toBe('该文件正在恢复，请稍后重试'))
  remote = 'remote after task'
  await act(async () => { await client.invalidateQueries({ queryKey: queryKeys.files.lists('alpha') }) })
  expect(result.current.fileContent).toBe('local draft')
  await waitFor(() => expect(result.current.originalFileContent).toBe(remote))
  status = 200
  act(() => result.current.setFileContent(''))
  await act(async () => { await result.current.handleFileSave() })
  expect(writes).toEqual([{ content: 'local draft' }, { content: '' }])
  expect(result.current.isEditDialogOpen).toBe(false)
})

it('retains recursive regex and size/date filters with the selected path', async () => {
  let received: unknown
  let requestedPath: string | null = null
  server.use(http.post('*/api/servers/alpha/files/search', async ({ request }) => {
    received = await request.json(); requestedPath = new URL(request.url).searchParams.get('path')
    return HttpResponse.json({ results: [], total_count: 0 })
  }))
  const filters = { regex: '\\.(toml|snbt)$', ignore_case: false, search_subfolders: true, min_size: 1, max_size: 1000, newer_than: '2026-01-01', older_than: '2026-09-25' }
  await fileApi.searchFiles('alpha', '/data/config', filters)
  expect(received).toEqual(filters)
  expect(requestedPath).toBe('/data/config')
})

it('keeps per-file overwrite policy and refreshes earlier writes when a later upload batch is cancelled', async () => {
  const secondStarted = deferred<void>()
  const finishSecond = deferred<void>()
  const files = Array.from({ length: FILES_PER_BATCH + 1 }, (_, index) => new File(['x'], `${index}.txt`))
  let batches = 0
  let policy: unknown
  let reusable: string | null = null
  client.setQueryData(queryKeys.files.list('alpha', '/data'), { items: [], current_path: '/data' })
  server.use(
    http.post('*/api/servers/alpha/files/upload/check', () => HttpResponse.json({ session_id: 'upload', conflicts: [{ path: '0.txt', type: 'file' }] })),
    http.post('*/api/servers/alpha/files/upload/policy', async ({ request }) => {
      policy = await request.json(); reusable = new URL(request.url).searchParams.get('reusable')
      return HttpResponse.json({ message: 'ok' })
    }),
    http.post('*/api/servers/alpha/files/upload/multiple', async () => {
      batches++
      if (batches === 2) { secondStarted.resolve(); await finishSecond.promise }
      return HttpResponse.json({ message: 'ok', results: { '0.txt': { status: 'success' }, '1.txt': { status: 'skipped', reason: 'no_decision' } } })
    }),
  )
  const { result, unmount } = renderHook(() => useMultiFileUpload(true, 'alpha', '/data', files), { wrapper })
  await act(async () => { await result.current.check() })
  expect(result.current.uploadState.step).toBe('conflicts')
  act(() => result.current.setPolicy({ mode: 'per_file', decisions: [{ path: '0.txt', overwrite: true }] }))
  let uploading!: Promise<void>
  act(() => { uploading = result.current.start() })
  await secondStarted.promise
  act(() => result.current.cancel())
  await act(async () => { await uploading })
  finishSecond.resolve()
  expect(policy).toEqual({ mode: 'per_file', decisions: [{ path: '0.txt', overwrite: true }] })
  expect(reusable).toBe('true')
  expect(batches).toBe(2)
  expect(result.current.uploadState.error).toContain('已写入的文件会保留')
  expect(client.getQueryState(queryKeys.files.list('alpha', '/data'))?.isInvalidated).toBe(true)
  unmount()
})
