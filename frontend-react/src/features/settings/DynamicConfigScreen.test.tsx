import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { api } from '@/shared/http/api'
import { createTestClient, httpResponse } from '@/test/http'
import { TestProviders } from '@/test/TestProviders'
import DynamicConfig from '@/features/settings/DynamicConfigScreen'

vi.mock('sonner', () => ({ toast: { loading: vi.fn(), dismiss: vi.fn(), warning: vi.fn() } }))
vi.mock('@/shared/editors/index', () => ({ MonacoDiffEditor: ({ original, modified }: { original: string; modified: string }) =>
  <div aria-label="比较结果">{original} → {modified}</div> }))
vi.mock('@/shared/forms/rjsfTheme', () => ({ default: ({ formData, onChange }: {
  formData: { setting: string }; onChange: (event: { formData: { setting: string } }) => void
}) => <input aria-label="配置项" value={formData.setting ?? ''} onChange={event => onChange({ formData: { setting: event.target.value } })} /> }))

const originalAdapter = api.defaults.adapter
let client: ReturnType<typeof createTestClient>
let remote: string
beforeEach(() => {
  client = createTestClient(); remote = '服务器配置'
  api.defaults.adapter = async config => {
    const schema = { module_name: 'test', json_schema: { title: '测试模块' } }
    if (config.url === '/config/modules') return httpResponse(config, { modules: { test: schema } })
    if (config.url?.endsWith('/schema')) return httpResponse(config, schema)
    return httpResponse(config, { module_name: 'test', config_data: { setting: remote } })
  }
})
afterEach(() => { api.defaults.adapter = originalAdapter; client.clear() })

it('preserves a dynamic configuration draft while fetching the comparison baseline', async () => {
  render(<TestProviders client={client} route="/config?module=test"><DynamicConfig /></TestProviders>)
  const editor = await screen.findByRole('textbox', { name: '配置项' })
  fireEvent.change(editor, { target: { value: '本地编辑' } })
  remote = '远端修改'
  fireEvent.click(screen.getByRole('button', { name: '差异对比' }))
  await waitFor(() => expect(screen.getByLabelText('比较结果').textContent).toContain('远端修改'))
  expect((editor as HTMLInputElement).value).toBe('本地编辑')
})
