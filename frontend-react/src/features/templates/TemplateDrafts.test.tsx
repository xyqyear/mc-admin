import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { Route, Routes } from 'react-router'
import type { VariableFormData } from '@/features/templates/ui/index'
import { convertToApiFormat, convertToFormData } from '@/features/templates/ui/variableUtils'
import { api, queryKeys } from '@/shared/http/api'
import { createTestClient, httpResponse } from '@/test/http'
import { TestProviders } from '@/test/TestProviders'
import TemplateEdit from '@/features/templates/TemplateEditScreen'
import DefaultVariables from '@/features/templates/DefaultVariablesScreen'

const toast = vi.hoisted(() => ({ error: vi.fn(), success: vi.fn(), warning: vi.fn() }))
vi.mock('sonner', () => ({ toast }))
vi.mock('@/shared/editors/index', () => ({
  ComposeYamlEditor: ({ value, onChange }: { value: string; onChange: (value: string) => void }) =>
    <textarea aria-label="模板 YAML" value={value} onChange={event => onChange(event.target.value)} />,
  MonacoDiffEditor: ({ original, modified }: { original: string; modified: string }) =>
    <div aria-label="比较结果">{original} → {modified}</div>,
}))
vi.mock('@/features/templates/ui/index', () => ({
  convertToApiFormat, convertToFormData,
  VariableDefinitionForm: ({ value, onChange }: { value: VariableFormData[]; onChange: (value: VariableFormData[]) => void }) =>
    <input aria-label="变量显示名" value={value[0]?.display_name ?? ''} onChange={event => onChange([{ ...value[0], display_name: event.target.value }])} />,
}))

const originalAdapter = api.defaults.adapter
const adapter = vi.fn()
let client: ReturnType<typeof createTestClient>
let remoteName: string
let failSave: boolean
const definitions = () => [{ name: 'memory', display_name: remoteName, type: 'string', default: '1G' }]
beforeEach(() => {
  vi.clearAllMocks()
  client = createTestClient(); api.defaults.adapter = adapter
  remoteName = '原始内容'; failSave = false
  adapter.mockImplementation(async config => {
    if (config.method === 'put' && failSave) return httpResponse(config, { detail: '保存被拒绝' }, 409)
    if (config.url === '/templates/default-variables') return httpResponse(config, { variable_definitions: definitions() })
    return httpResponse(config, { id: 1, name: remoteName, description: '说明', yaml_template: `memory: {memory}\n# ${remoteName}`, variable_definitions: definitions() })
  })
})
afterEach(() => { api.defaults.adapter = originalAdapter; client.clear() })

it('preserves the entire template draft when comparison reads remote changes', async () => {
  render(<TestProviders client={client} route="/templates/1/edit"><Routes>
    <Route path="/templates/:id/edit" element={<TemplateEdit />} />
  </Routes></TestProviders>)
  const name = await screen.findByRole('textbox', { name: '模板名称' })
  fireEvent.change(name, { target: { value: '本地名称' } })
  fireEvent.change(screen.getByRole('textbox', { name: '模板 YAML' }), { target: { value: 'memory: {memory}\n# 本地配置' } })
  fireEvent.change(screen.getByRole('textbox', { name: '变量显示名' }), { target: { value: '本地变量' } })
  remoteName = '远端修改'
  fireEvent.click(screen.getByRole('button', { name: '差异对比' }))
  await waitFor(() => expect(screen.getByLabelText('比较结果').textContent).toContain('远端修改'))
  expect((name as HTMLInputElement).value).toBe('本地名称')
  expect((screen.getByRole('textbox', { name: '模板 YAML', hidden: true }) as HTMLTextAreaElement).value).toContain('本地配置')
  expect((screen.getByRole('textbox', { name: '变量显示名', hidden: true }) as HTMLInputElement).value).toBe('本地变量')
})

it('keeps default variable edits across remote refresh and a failed save', async () => {
  render(<TestProviders client={client}><DefaultVariables /></TestProviders>)
  const input = await screen.findByRole('textbox', { name: '变量显示名' })
  fireEvent.change(input, { target: { value: '本地变量' } })
  remoteName = '远端变量'
  await act(async () => { await client.invalidateQueries({ queryKey: queryKeys.templates.defaultVariables() }) })
  await waitFor(() => expect(client.getQueryData<{ variable_definitions: { display_name: string }[] }>(queryKeys.templates.defaultVariables())?.variable_definitions[0].display_name).toBe('远端变量'))
  expect((input as HTMLInputElement).value).toBe('本地变量')
  failSave = true
  fireEvent.click(screen.getByRole('button', { name: '保存' }))
  await waitFor(() => expect(toast.error).toHaveBeenCalled())
  expect((input as HTMLInputElement).value).toBe('本地变量')
})

it('keeps an edited template available for retry after save fails', async () => {
  render(<TestProviders client={client} route="/templates/1/edit"><Routes>
    <Route path="/templates/:id/edit" element={<TemplateEdit />} />
    <Route path="/templates" element={<div>模板列表</div>} />
  </Routes></TestProviders>)
  const name = await screen.findByRole('textbox', { name: '模板名称' })
  fireEvent.change(name, { target: { value: '本地模板' } })
  failSave = true
  fireEvent.click(screen.getByRole('button', { name: '保存' }))
  await waitFor(() => expect(toast.error).toHaveBeenCalledWith('更新失败: 保存被拒绝'))
  expect((name as HTMLInputElement).value).toBe('本地模板')
  expect(screen.queryByText('模板列表')).toBeNull()
})
