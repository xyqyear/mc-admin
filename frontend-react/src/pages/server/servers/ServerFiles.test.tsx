import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { Route, Routes } from 'react-router'
import type { AxiosResponse } from 'axios'
import { api, queryKeys } from '@/shared/http/api'
import { createTestClient, deferred, httpResponse } from '@/test/http'
import { TestProviders } from '@/test/TestProviders'
import ServerFiles from '@/pages/server/servers/ServerFiles'

const toast = vi.hoisted(() => ({ error: vi.fn(), success: vi.fn(), info: vi.fn(), warning: vi.fn() }))
vi.mock('sonner', () => ({ toast }))
vi.mock('@/shared/editors/index', () => ({
  SimpleEditor: ({ value, onChange }: { value: string; onChange: (value: string) => void }) =>
    <textarea aria-label="文件内容" value={value} onChange={event => onChange(event.target.value)} />,
}))
vi.mock('@/features/files/components/dialogs/index', async () => ({
  FileEditDialog: (await import('@/features/files/components/dialogs/FileEditDialog')).default,
  ...Object.fromEntries(['MultiFileUploadDialog', 'CreateDialog', 'RenameDialog', 'FileDiffDialog', 'CompressionConfirmDialog', 'CompressionResultDialog', 'FileDeepSearchDialog'].map(name => [name, () => null])),
}))
vi.mock('@/features/archives/ui/ArchiveSelectionDialog', () => ({ default: () => null }))
vi.mock('@/features/archives/ui/PopulateProgressDialog', () => ({ default: () => null }))
vi.mock('@/features/files/components/FileToolbar', () => ({ default: ({ onRefresh }: { onRefresh: () => void }) => <button onClick={onRefresh}>刷新列表</button> }))
vi.mock('@/features/files/components/FileTable', () => ({ default: ({ onFileEdit }: { onFileEdit: (file: object) => void }) =>
  <button onClick={() => onFileEdit({ name: 'server.properties', path: '/server.properties', type: 'file' })}>编辑配置</button>,
}))

const originalAdapter = api.defaults.adapter
let client: ReturnType<typeof createTestClient>
const adapter = vi.fn()
beforeEach(() => {
  vi.clearAllMocks()
  client = createTestClient()
  api.defaults.adapter = adapter
  adapter.mockImplementation(async config => {
    if (config.url.endsWith('/files/content')) return httpResponse(config, { content: 'original' })
    if (config.url.endsWith('/files')) return httpResponse(config, { items: [], path: '/' })
    return httpResponse(config, { id: 'server', name: 'server', serverType: 'vanilla' })
  })
})
afterEach(() => { api.defaults.adapter = originalAdapter; client.clear() })

function showFiles() {
  render(<TestProviders client={client} route="/server/server/files"><Routes>
    <Route path="/server/:id/files" element={<ServerFiles />} />
  </Routes></TestProviders>)
}

it('blocks saving while content is loading or unavailable', async () => {
  const content = deferred<AxiosResponse>()
  adapter.mockImplementation(async config => {
    if (config.url.endsWith('/files/content')) return content.promise
    if (config.url.endsWith('/files')) return httpResponse(config, { items: [] })
    return httpResponse(config, { serverType: 'vanilla' })
  })
  showFiles()
  fireEvent.click(await screen.findByText('编辑配置'))
  expect((screen.getByRole('button', { name: '保存' }) as HTMLButtonElement).disabled).toBe(true)
  await act(async () => { content.reject(new Error('读取失败')) })
  await waitFor(() => expect(screen.getByText(/读取失败/)).toBeTruthy())
  expect((screen.getByRole('button', { name: '保存' }) as HTMLButtonElement).disabled).toBe(true)
})

it('retains a failed save and dirty draft during remote refresh, then saves an intentional empty file', async () => {
  showFiles()
  fireEvent.click(await screen.findByText('编辑配置'))
  const editor = await screen.findByRole('textbox', { name: '文件内容' })
  await waitFor(() => expect((editor as HTMLTextAreaElement).value).toBe('original'))
  fireEvent.change(editor, { target: { value: 'authored draft' } })
  adapter.mockImplementation(async config => {
    if (config.method === 'post') return httpResponse(config, { detail: '磁盘写入失败' }, 500)
    if (config.url.endsWith('/files/content')) return httpResponse(config, { content: 'remote edit' })
    return httpResponse(config, { items: [] })
  })
  fireEvent.click(screen.getByRole('button', { name: '保存' }))
  await waitFor(() => expect(toast.error).toHaveBeenCalled())
  expect((screen.getByRole('textbox', { name: '文件内容' }) as HTMLTextAreaElement).value).toBe('authored draft')
  await act(async () => { await client.invalidateQueries({ queryKey: queryKeys.files.content('server', '/server.properties') }) })
  expect((screen.getByRole('textbox', { name: '文件内容' }) as HTMLTextAreaElement).value).toBe('authored draft')
  adapter.mockImplementation(async config => httpResponse(config, config.method === 'post' ? { message: '成功' } : { items: [] }))
  fireEvent.change(editor, { target: { value: '' } })
  fireEvent.click(screen.getByRole('button', { name: '保存' }))
  await waitFor(() => expect(adapter.mock.calls.some(([config]) => config.method === 'post' && JSON.parse(config.data).content === '')).toBe(true))
  await waitFor(() => expect(screen.queryByRole('textbox', { name: '文件内容' })).toBeNull())
})

it('reports a failed list refresh without a success notification', async () => {
  showFiles()
  await waitFor(() => expect(client.getQueryData(queryKeys.files.list('server', '/'))).toBeDefined())
  adapter.mockImplementation(async config => httpResponse(config, { detail: '暂时不可用' }, 503))
  fireEvent.click(screen.getByText('刷新列表'))
  await waitFor(() => expect(toast.error).toHaveBeenCalledWith('刷新失败'))
  expect(toast.success).not.toHaveBeenCalled()
})
