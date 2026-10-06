// @vitest-environment node
import { JSDOM } from 'jsdom'
import { act, renderHook } from '@testing-library/react'
import { afterAll, afterEach, beforeAll, beforeEach, expect, it, vi } from 'vitest'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { createTestClient } from '@/test/http'
import { TestProviders } from '@/test/TestProviders'

const dom = new JSDOM('', { url: 'http://localhost:3000' })
const server = setupServer()
let useMultiFileUpload: typeof import('@/features/files/useMultiFileUpload').useMultiFileUpload
beforeAll(async () => {
  vi.stubGlobal('window', dom.window)
  vi.stubGlobal('document', dom.window.document)
  ;({ useMultiFileUpload } = await import('@/features/files/useMultiFileUpload'))
  server.listen({ onUnhandledRequest: 'error' })
})
afterAll(() => { server.close(); vi.unstubAllGlobals(); dom.window.close() })
let client: ReturnType<typeof createTestClient>
beforeEach(() => { client = createTestClient() })
afterEach(() => { client.clear(); server.resetHandlers() })

it('keeps same-name folder uploads distinct through conflict checks, multipart bytes and mixed results', async () => {
  const selected = (path: string, content: string) => {
    const file = new File([content], path.split('/').at(-1)!)
    Object.defineProperty(file, 'webkitRelativePath', { value: path })
    return file
  }
  const files = [selected('dir-a/config.toml', 'alpha'), selected('dir-b/config.toml', 'beta'), selected('dir-b/nested/config.toml', 'gamma')]
  let structure: unknown
  let policy: unknown
  const multipart = new Map<string, string>()
  server.use(
    http.post('*/api/servers/alpha/files/upload/check', async ({ request }) => {
      structure = await request.json()
      return HttpResponse.json({ session_id: 'folders', conflicts: files.map(file => ({ path: file.webkitRelativePath, type: 'file' })) })
    }),
    http.post('*/api/servers/alpha/files/upload/policy', async ({ request }) => { policy = await request.json(); return HttpResponse.json({ message: 'ok' }) }),
    http.post('*/api/servers/alpha/files/upload/multiple', async ({ request }) => {
      for (const entry of (await request.formData()).getAll('files')) {
        if (typeof entry === 'string') throw new Error('expected a file part')
        multipart.set(entry.name, await entry.text())
      }
      return HttpResponse.json({ message: 'ok', results: {
        'dir-a/config.toml': { status: 'success' },
        'dir-b/config.toml': { status: 'skipped', reason: 'no_overwrite' },
        'dir-b/nested/config.toml': { status: 'failed', reason: '拒绝写入' },
      } })
    }),
  )
  const { result } = renderHook(() => useMultiFileUpload(true, 'alpha', '/data', files), {
    wrapper: ({ children }) => <TestProviders client={client}>{children}</TestProviders>,
  })
  await act(async () => { await result.current.check() })
  expect(structure).toEqual({ files: [
    { path: 'dir-a', name: 'dir-a', type: 'directory' }, { path: 'dir-a/config.toml', name: 'config.toml', type: 'file', size: 5 },
    { path: 'dir-b', name: 'dir-b', type: 'directory' }, { path: 'dir-b/config.toml', name: 'config.toml', type: 'file', size: 4 },
    { path: 'dir-b/nested', name: 'nested', type: 'directory' }, { path: 'dir-b/nested/config.toml', name: 'config.toml', type: 'file', size: 5 },
  ] })
  const decisions = [{ path: 'dir-a/config.toml', overwrite: true }, { path: 'dir-b/config.toml', overwrite: false }, { path: 'dir-b/nested/config.toml', overwrite: true }]
  act(() => result.current.setPolicy({ mode: 'per_file', decisions }))
  await act(async () => { await result.current.start() })
  expect(policy).toEqual({ mode: 'per_file', decisions })
  expect(multipart).toEqual(new Map([['dir-a/config.toml', 'alpha'], ['dir-b/config.toml', 'beta'], ['dir-b/nested/config.toml', 'gamma']]))
  expect(result.current.uploadState.results).toEqual({
    'dir-a/config.toml': { status: 'success' },
    'dir-b/config.toml': { status: 'skipped', reason: 'no_overwrite' },
    'dir-b/nested/config.toml': { status: 'failed', reason: '拒绝写入' },
  })
})
