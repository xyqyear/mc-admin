import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterAll, afterEach, beforeAll, beforeEach, expect, it, vi } from 'vitest'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { createTestClient } from '@/test/http'
import { TestProviders } from '@/test/TestProviders'
import FileDeepSearchDialog from './FileDeepSearchDialog'

const server = setupServer()
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterAll(() => server.close())
let client: ReturnType<typeof createTestClient>
beforeEach(() => { client = createTestClient() })
afterEach(() => { client.clear(); server.resetHandlers() })

it.each([
  { kind: 'file', currentPath: '/data', resultPath: '/config/a.toml', resultType: 'file', selected: 'a.toml', destination: ['/data/config', 'a.toml'] },
  { kind: 'directory', currentPath: '/data', resultPath: '/config', resultType: 'directory', selected: 'config', destination: ['/data/config'] },
  { kind: 'virtual directory', currentPath: '/data', resultPath: '/config/a.toml', resultType: 'file', selected: 'config', destination: ['/data/config', 'config|toml', true] },
  { kind: 'root file', currentPath: '/', resultPath: '/config/a.toml', resultType: 'file', selected: 'a.toml', destination: ['/config', 'a.toml'] },
])('navigates a $kind result with its current directory and search identity', async ({ currentPath, resultPath, resultType, selected, destination }) => {
  const navigate = vi.fn()
  const searches: unknown[] = []
  server.use(http.post('*/api/servers/alpha/files/search', async ({ request }) => {
    searches.push({ path: new URL(request.url).searchParams.get('path'), body: await request.json() })
    return HttpResponse.json({ results: [{ path: resultPath, name: resultType === 'file' ? 'a.toml' : 'config', type: resultType, size: 5, modified_at: 1 }], total_count: 1 })
  }))
  render(<TestProviders client={client}><FileDeepSearchDialog open serverId="alpha" currentPath={currentPath} onCancel={() => {}} onNavigate={navigate} /></TestProviders>)
  fireEvent.change(screen.getByLabelText('搜索模式'), { target: { value: 'config|toml' } })
  fireEvent.click(screen.getByRole('button', { name: '搜索' }))
  await screen.findByText('搜索结果 (1 个文件)')
  const row = await screen.findByText((_, element) => element?.tagName === 'SPAN' && element.textContent === selected)
  fireEvent.click(row)
  await waitFor(() => expect(navigate).toHaveBeenCalledExactlyOnceWith(...destination))
  expect(searches).toEqual([{ path: currentPath, body: { regex: 'config|toml', ignore_case: true, search_subfolders: true } }])
})
