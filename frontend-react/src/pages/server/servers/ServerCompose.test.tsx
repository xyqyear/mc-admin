import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { Route, Routes } from 'react-router'
import { api, queryKeys } from '@/shared/http/api'
import { createTestClient, httpResponse } from '@/test/http'
import { TestProviders } from '@/test/TestProviders'
import ServerCompose from '@/pages/server/servers/ServerCompose'

const toast = vi.hoisted(() => ({ error: vi.fn(), success: vi.fn(), info: vi.fn(), warning: vi.fn() }))
vi.mock('sonner', () => ({ toast }))
vi.mock('@/shared/editors/index', () => ({
  ComposeYamlEditor: ({ value, onChange }: { value: string; onChange: (value: string) => void }) =>
    <textarea aria-label="Compose 内容" value={value} onChange={event => onChange(event.target.value)} />,
  MonacoDiffEditor: ({ original, modified }: { original: string; modified: string }) =>
    <div aria-label="比较结果">{original} → {modified}</div>,
}))
vi.mock('@/shared/forms/rjsfTheme', () => ({ default: ({ formData, onChange }: {
  formData: Record<string, string>; onChange: (event: { formData: Record<string, string> }) => void
}) => <input aria-label="模板参数" value={formData.memory ?? ''} onChange={event => onChange({ formData: { memory: event.target.value } })} /> }))
vi.mock('@/features/configuration/components/RebuildProgressDialog', () => ({ default: () => null }))
vi.mock('@/features/configuration/components/ConvertModeDialog', () => ({ default: () => null }))
vi.mock('@/shared/editors/DockerComposeHelpDialog', () => ({ default: () => null }))

const originalAdapter = api.defaults.adapter
let client: ReturnType<typeof createTestClient>
const adapter = vi.fn()
let remote = 'original compose'
let templateMode = false
beforeEach(() => {
  vi.clearAllMocks(); remote = 'original compose'; templateMode = false
  client = createTestClient(); api.defaults.adapter = adapter
  adapter.mockImplementation(async config => {
    if (config.url.endsWith('/compose')) return httpResponse(config, { yaml_content: remote, version: remote || "empty" })
    if (config.url.endsWith('/template-config/preview')) return httpResponse(config, { is_template_based: templateMode })
    if (config.url.endsWith('/template-config')) return httpResponse(config, { version: remote || "empty", template_id: 1, variable_values: { memory: remote }, json_schema: {}, template_name: 'template' })
    return httpResponse(config, { serverType: 'vanilla', name: 'server' })
  })
})
afterEach(() => { api.defaults.adapter = originalAdapter; client.clear() })
function showCompose() {
  render(<TestProviders client={client} route="/server/server/compose"><Routes>
    <Route path="/server/:id/compose" element={<ServerCompose />} />
  </Routes></TestProviders>)
}

it('preserves a Compose draft when comparison fetches changed remote content', async () => {
  showCompose()
  const editor = await screen.findByRole('textbox', { name: 'Compose 内容' })
  await waitFor(() => expect((editor as HTMLTextAreaElement).value).toBe(remote))
  fireEvent.change(editor, { target: { value: 'authored compose' } })
  remote = 'changed remote'
  fireEvent.click(screen.getByRole('button', { name: '差异对比' }))
  await waitFor(() => expect(screen.getByLabelText('比较结果').textContent).toContain('changed remote → authored compose'))
  expect((editor as HTMLTextAreaElement).value).toBe('authored compose')
})

it('keeps an open dirty editor after a background Compose fetch fails', async () => {
  showCompose()
  const editor = await screen.findByRole('textbox', { name: 'Compose 内容' })
  fireEvent.change(editor, { target: { value: 'retained draft' } })
  adapter.mockImplementation(async config => httpResponse(config, { detail: '无法读取' }, 403))
  await act(async () => { await client.invalidateQueries({ queryKey: queryKeys.compose.detail('server') }) })
  await waitFor(() => expect(client.getQueryState(queryKeys.compose.detail('server'))?.status).toBe('error'))
  expect((screen.getByRole('textbox', { name: 'Compose 内容' }) as HTMLTextAreaElement).value).toBe('retained draft')
})

it('retains authored template parameters when remote template configuration changes', async () => {
  templateMode = true
  showCompose()
  const editor = await screen.findByRole('textbox', { name: '模板参数' })
  fireEvent.change(editor, { target: { value: 'authored parameters' } })
  remote = 'changed parameters'
  await act(async () => { await client.invalidateQueries({ queryKey: queryKeys.templates.serverConfig('server') }) })
  expect((editor as HTMLInputElement).value).toBe('authored parameters')
})

it.each([false, true])('reloads the latest remote content only after confirmation (template=%s)', async mode => {
  templateMode = mode
  showCompose()
  const label = mode ? '模板参数' : 'Compose 内容'
  const editor = await screen.findByRole('textbox', { name: label })
  fireEvent.change(editor, { target: { value: 'discarded draft' } })
  remote = ''
  fireEvent.click(screen.getByRole('button', { name: '重新载入' }))
  expect((editor as HTMLInputElement).value).toBe('discarded draft')
  fireEvent.click(await screen.findByRole('button', { name: '确认' }))
  await waitFor(() => expect((screen.getByRole('textbox', { name: label }) as HTMLInputElement).value).toBe(''))
  expect(toast.info).toHaveBeenCalled()
})

it('retains the Compose draft when confirmed reload or save fails', async () => {
  showCompose()
  const editor = await screen.findByRole('textbox', { name: 'Compose 内容' })
  fireEvent.change(editor, { target: { value: 'retryable compose' } })
  adapter.mockImplementation(async config => httpResponse(config, { detail: '操作失败' }, 409))
  fireEvent.click(screen.getByRole('button', { name: '重新载入' }))
  fireEvent.click(await screen.findByRole('button', { name: '确认' }))
  await waitFor(() => expect(toast.error).toHaveBeenCalledWith('重新载入失败，已保留编辑内容'))
  expect((editor as HTMLTextAreaElement).value).toBe('retryable compose')
  await waitFor(() => expect(screen.queryByRole('alertdialog')).toBeNull())
  adapter.mockImplementation(async config => config.method === 'get' ? httpResponse(config, { yaml_content: remote, version: remote }) : httpResponse(config, { detail: '操作失败' }, 409))
  fireEvent.click(screen.getByRole('button', { name: '提交并重建' }))
  fireEvent.click(await screen.findByRole('button', { name: '确认重建' }))
  await waitFor(() => expect(toast.error).toHaveBeenCalledWith('配置提交失败: 操作失败'))
  expect((editor as HTMLTextAreaElement).value).toBe('retryable compose')
  expect(screen.getByRole('button', { name: '确认重建' })).toBeTruthy()
})
