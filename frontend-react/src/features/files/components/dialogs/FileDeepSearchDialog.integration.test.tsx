import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterAll, afterEach, beforeAll, beforeEach, expect, it, vi } from 'vitest'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { createTestClient } from '@/test/http'
import { TestProviders } from '@/test/TestProviders'
import FileDeepSearchDialog from './FileDeepSearchDialog'
import { FileSnapshotRecovery } from '../FileSnapshotRecovery'
import { SnapshotRecoveryContext } from '../../snapshotRecoveryContext'

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
  render(<TestProviders client={client}><SnapshotRecoveryContext.Provider value={{ busy: false, create: vi.fn(), restore: vi.fn(), history: vi.fn() }}><FileDeepSearchDialog open serverId="alpha" currentPath={currentPath} onCancel={() => {}} onNavigate={navigate} /></SnapshotRecoveryContext.Provider></TestProviders>)
  fireEvent.change(screen.getByLabelText('搜索模式'), { target: { value: 'config|toml' } })
  fireEvent.click(screen.getByRole('button', { name: '搜索' }))
  await screen.findByText('搜索结果 (1 个文件)')
  const row = await screen.findByText((_, element) => element?.tagName === 'SPAN' && element.textContent === selected)
  fireEvent.click(row)
  await waitFor(() => expect(navigate).toHaveBeenCalledExactlyOnceWith(...destination))
  expect(searches).toEqual([{ path: currentPath, body: { regex: 'config|toml', ignore_case: true, search_subfolders: true } }])
})

it('creates one multi-path snapshot from checked real results using the captured search root', async () => {
  let ruleReads = 0
  const created: unknown[] = []
  server.use(
    http.post('*/api/servers/alpha/files/search', () => HttpResponse.json({ search_path: '/captured', results: [
      { path: '/plugins', name: 'plugins', type: 'directory', size: 0, modified_at: 1 },
      { path: '/plugins/a.toml', name: 'a.toml', type: 'file', size: 3, modified_at: 1 },
      { path: '/virtual/b.toml', name: 'b.toml', type: 'file', size: 5, modified_at: 1 },
    ], total_count: 3 })),
    http.get('*/api/snapshots/restorations/active', () => HttpResponse.json({ restorations: [], total: 0 })),
    http.get('*/api/servers/alpha', () => HttpResponse.json({ id: 'alpha', name: 'Alpha', serverType: 'VANILLA', server_generation: 1 })),
    http.get('*/api/snapshots/targets/rules', () => { ruleReads++; return HttpResponse.json({ server_id: 'alpha', server_generation: 1, ignored_paths: [], rules_version: 'v1' }) }),
    http.post('*/api/snapshots', async ({ request }) => { created.push(await request.json()); return HttpResponse.json({ task_id: 'snapshot' }, { status: 202 }) }),
    http.get('*/api/tasks/snapshot', () => HttpResponse.json({ task_id: 'snapshot', status: 'completed', result: { snapshot: { id: 'a'.repeat(64), short_id: 'aaaaaaaa', note: '多选备份' }, note_warning: null } })),
  )
  render(<TestProviders client={client}><FileSnapshotRecovery serverId="alpha"><FileDeepSearchDialog open serverId="alpha" currentPath="/data" onCancel={() => {}} onNavigate={vi.fn()} /></FileSnapshotRecovery></TestProviders>)
  fireEvent.change(screen.getByLabelText('搜索模式'), { target: { value: 'toml|plugins' } })
  fireEvent.click(screen.getByRole('button', { name: '搜索' }))
  fireEvent.click(await screen.findByRole('checkbox', { name: '选择搜索结果 /plugins' }))
  fireEvent.click(screen.getByRole('checkbox', { name: '选择搜索结果 /virtual' }))
  expect(screen.getByRole('checkbox', { name: '选择搜索结果 /virtual/b.toml' }).getAttribute('aria-checked')).toBe('true')
  fireEvent.change(screen.getByLabelText('搜索模式'), { target: { value: 'another draft' } })
  const create = screen.getByRole('button', { name: '创建快照' })
  await waitFor(() => expect((create as HTMLButtonElement).disabled).toBe(false))
  fireEvent.click(create)
  fireEvent.change(await screen.findByLabelText('快照备注（可选）'), { target: { value: '多选备份' } })
  const dialog = screen.getByRole('dialog', { name: '确认创建快照' })
  fireEvent.click(within(dialog).getByRole('button', { name: '创建快照' }))
  await waitFor(() => expect(created).toEqual([{ scope: { kind: 'paths', server_id: 'alpha', paths: ['captured/plugins', 'captured/virtual/b.toml'] }, note: '多选备份' }]))
  expect(ruleReads).toBe(1)
  expect(screen.getByText('已选择 2 个条目')).toBeTruthy()
})
