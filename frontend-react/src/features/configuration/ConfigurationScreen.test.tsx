import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterAll, afterEach, beforeAll, beforeEach, expect, it, vi } from 'vitest'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { Route, Routes } from 'react-router'
import { queryKeys } from '@/shared/http/api'
import { createTestClient, deferred } from '@/test/http'
import { TestProviders } from '@/test/TestProviders'
import ConfigurationScreen from '@/features/configuration/ConfigurationScreen'
import { OperationObserver } from '@/app/operations/OperationObserver'

const toast = vi.hoisted(() => ({ error: vi.fn(), success: vi.fn(), info: vi.fn() }))
vi.mock('sonner', () => ({ toast }))
vi.mock('@/shared/editors/index', () => ({
  ComposeYamlEditor: ({ value, onChange }: { value: string; onChange: (value: string) => void }) => <textarea aria-label="Compose 内容" value={value} onChange={event => onChange(event.target.value)} />,
  MonacoDiffEditor: ({ original, modified, originalTitle, modifiedTitle }: { original: string; modified: string; originalTitle?: string; modifiedTitle?: string }) => <div aria-label="比较结果">{originalTitle}: {original} → {modifiedTitle}: {modified}</div>,
}))
vi.mock('@/shared/forms/rjsfTheme', () => ({ default: ({ formData, onChange }: {
  formData: Record<string, string>; onChange: (event: { formData: Record<string, string> }) => void
}) => <input aria-label="模板参数" value={formData.memory ?? ''} onChange={event => onChange({ formData: { memory: event.target.value } })} /> }))
vi.mock('@/shared/editors/DockerComposeHelpDialog', () => ({ default: () => null }))

const server = setupServer()
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterAll(() => server.close())
let client: ReturnType<typeof createTestClient>
let remote: string
let version: string
let templateMode: boolean
let submissions: Record<string, unknown>[]
const template = () => ({ version, template_id: 1, template_name: '模板', yaml_template: '{{ memory }}', variable_values: { memory: remote }, json_schema: {}, variable_definitions: [], has_template_update: true })
beforeEach(() => {
  client = createTestClient(); remote = 'online v1'; version = 'v1'; templateMode = false; submissions = []; vi.clearAllMocks()
  server.use(
    http.get('*/api/servers/alpha', () => HttpResponse.json({ name: 'alpha', serverType: 'vanilla' })),
    http.get('*/api/servers/alpha/compose', () => HttpResponse.json({ yaml_content: remote, version })),
    http.get('*/api/servers/alpha/template-config/preview', () => HttpResponse.json({ is_template_based: templateMode, template_id: templateMode ? 1 : null })),
    http.get('*/api/servers/alpha/template-config', () => HttpResponse.json(template())),
    http.get('*/api/templates/', () => HttpResponse.json([{ id: 1, name: '模板' }])),
    http.post('*/api/servers/alpha/compose', async ({ request }) => { submissions.push(await request.json() as Record<string, unknown>); return HttpResponse.json({ task_id: 'task' }) }),
    http.put('*/api/servers/alpha/template-config', async ({ request }) => { submissions.push(await request.json() as Record<string, unknown>); return HttpResponse.json({ task_id: 'task' }) }),
    http.get('*/api/tasks/task', () => HttpResponse.json({ task_id: 'task', task_type: 'server_rebuild', status: 'running', progress: 20, created_at: '2026-09-25T12:00:00Z', message: '应用中' })),
  )
})
afterEach(() => { client.clear(); server.resetHandlers() })
function show(observe = false) {
  return render(<TestProviders client={client} route="/server/alpha/compose">{observe && <OperationObserver sessionId="owner" />}<Routes><Route path="/server/:id/compose" element={<ConfigurationScreen />} /></Routes></TestProviders>)
}
async function edit(value = 'local draft') {
  const editor = await screen.findByRole('textbox', { name: templateMode ? '模板参数' : 'Compose 内容' })
  fireEvent.change(editor, { target: { value } }); return editor as HTMLInputElement
}
async function acceptCompared() {
  fireEvent.click(await screen.findByRole('button', { name: '比较并解决冲突' }))
  const accept = await screen.findByRole('button', { name: '接受此版本为新基准' })
  await waitFor(() => expect((accept as HTMLButtonElement).disabled).toBe(false))
  fireEvent.click(accept)
  await waitFor(() => expect(screen.queryByRole('button', { name: '接受此版本为新基准' })).toBeNull())
}
async function submit() {
  fireEvent.click(screen.getByRole('button', { name: '提交并重建' }))
  fireEvent.click(await screen.findByRole('button', { name: '确认重建' }))
}

it('waits for the first Compose response and treats an intentional empty draft as writable', async () => {
  const response = deferred<void>()
  server.use(http.get('*/api/servers/alpha/compose', async () => { await response.promise; return HttpResponse.json({ yaml_content: remote, version }) }))
  show()
  expect(screen.queryByRole('textbox', { name: 'Compose 内容' })).toBeNull()
  response.resolve()
  await edit('')
  await submit()
  await waitFor(() => expect(submissions).toEqual([{ yaml_content: '', expected_version: 'v1' }]))
})

it.each([false, true])('refreshes an untouched editor opened from stale cached configuration (template=%s)', async mode => {
  templateMode = mode
  const initial = show()
  await screen.findByRole('textbox', { name: mode ? '模板参数' : 'Compose 内容' })
  initial.unmount()
  remote = 'completed while away'; version = 'v2'
  const released = deferred<void>()
  server.use(
    http.get('*/api/servers/alpha/compose', async () => { await released.promise; return HttpResponse.json({ yaml_content: remote, version }) }),
    http.get('*/api/servers/alpha/template-config', async () => { await released.promise; return HttpResponse.json(template()) }),
  )
  await client.invalidateQueries({ queryKey: mode ? queryKeys.templates.serverConfig('alpha') : queryKeys.compose.detail('alpha') })
  show()
  const editor = await screen.findByRole('textbox', { name: mode ? '模板参数' : 'Compose 内容' }) as HTMLInputElement
  expect(editor.value).toBe('online v1')
  await act(async () => released.resolve())
  await waitFor(() => expect(editor.value).toBe('completed while away'))
  expect(screen.queryByText('在线配置已变更')).toBeNull()
  await submit()
  await waitFor(() => expect(submissions[0]?.expected_version).toBe('v2'))
})

it.each([false, true])('requires explicit comparison before resubmitting a retained draft (template=%s)', async mode => {
  templateMode = mode; show(); const editor = await edit()
  remote = 'online v2'; version = 'v2'
  fireEvent.click(screen.getByRole('button', { name: '提交并重建' }))
  await screen.findByText('在线配置已变更')
  expect(submissions).toHaveLength(0)
  expect(editor.value).toBe('local draft')
  fireEvent.click(screen.getByRole('button', { name: '比较并解决冲突' }))
  await screen.findByRole('button', { name: '接受此版本为新基准' })
  const comparisons = screen.getAllByLabelText('比较结果').map(element => element.textContent).join('\n')
  expect(comparisons).toContain('online v1'); expect(comparisons).toContain('online v2'); expect(comparisons).toContain('local draft')
  fireEvent.click(screen.getByRole('button', { name: '接受此版本为新基准' }))
  await waitFor(() => expect(screen.queryByRole('button', { name: '接受此版本为新基准' })).toBeNull())
  await submit()
  await waitFor(() => expect(submissions[0]).toEqual(mode ? { variable_values: { memory: 'local draft' }, expected_version: 'v2' } : { yaml_content: 'local draft', expected_version: 'v2' }))
})

it('keeps a second race as a conflict instead of automatically retrying with its advertised version', async () => {
  server.use(http.post('*/api/servers/alpha/compose', async ({ request }) => {
    submissions.push(await request.json() as Record<string, unknown>)
    remote = 'online v2'; version = 'v2'
    return HttpResponse.json({ detail: { code: 'configuration_conflict', message: '配置已被其他操作修改，请重新比较后提交', current_version: 'v2' } }, { status: 409 })
  }))
  show(); const editor = await edit(); await submit()
  await screen.findByText('在线配置已变更')
  expect(submissions).toEqual([{ yaml_content: 'local draft', expected_version: 'v1' }])
  await acceptCompared()
  server.use(http.post('*/api/servers/alpha/compose', async ({ request }) => { submissions.push(await request.json() as Record<string, unknown>); return HttpResponse.json({ task_id: 'task' }) }))
  await submit()
  await waitFor(() => expect(submissions[1]?.expected_version).toBe('v2'))
  expect(editor.value).toBe('local draft')
})

it.each([false, true])('retains the draft and exposes async final-check conflicts (template=%s)', async mode => {
  templateMode = mode
  server.use(http.get('*/api/tasks/task', () => {
    remote = 'changed while queued'; version = 'v2'
    return HttpResponse.json({ task_id: 'task', task_type: 'server_rebuild', status: 'failed', created_at: '2026-09-25T12:00:00Z', error: '配置已变更', error_code: 'configuration_conflict' })
  }))
  show(); const editor = await edit(); await submit()
  await screen.findByText('在线配置已变更')
  expect(editor.value).toBe('local draft')
  await acceptCompared()
  expect(editor.value).toBe('local draft')
})

it.each([403, 422, 500, 'network'] as const)('preserves the Compose draft after a failed write (%s)', async status => {
  server.use(http.post('*/api/servers/alpha/compose', () => status === 'network' ? HttpResponse.error() : HttpResponse.json({ detail: '保存失败' }, { status })))
  show(); const editor = await edit(); await submit()
  await waitFor(() => expect(toast.error).toHaveBeenCalled())
  expect(editor.value).toBe('local draft')
  expect(screen.getByRole('button', { name: '确认重建' })).toBeTruthy()
})

it('retains the current editor when another user changes the editing mode', async () => {
  show(); const editor = await edit()
  templateMode = true; remote = 'new template'; version = 'v2'
  await act(async () => { await client.invalidateQueries({ queryKey: queryKeys.templates.serverConfigPreview('alpha') }); await client.invalidateQueries({ queryKey: queryKeys.compose.detail('alpha') }) })
  await screen.findByText('在线编辑模式已变更')
  expect(editor.value).toBe('local draft')
  expect(screen.queryByRole('textbox', { name: '模板参数' })).toBeNull()
})

it('converts to direct mode with a version and retains the conversion dialog on conflict', async () => {
  templateMode = true
  server.use(http.post('*/api/servers/alpha/convert-to-direct', async ({ request }) => {
    submissions.push(await request.json() as Record<string, unknown>)
    remote = 'new remote'; version = 'v2'
    return HttpResponse.json({ detail: { code: 'configuration_conflict', message: '配置已变更', current_version: version } }, { status: 409 })
  }))
  show(); await edit()
  fireEvent.click(screen.getByRole('button', { name: '转换为直接编辑' }))
  fireEvent.click(await screen.findByRole('button', { name: '确认转换' }))
  await screen.findByText('在线配置已变更')
  expect(submissions).toEqual([{ expected_version: 'v1' }])
  await acceptCompared()
  expect(screen.getByRole('button', { name: '确认转换' })).toBeTruthy()
})

it('keeps conversion variables when a check detects a newer server configuration', async () => {
  templateMode = true
  server.use(
    http.post('*/api/servers/alpha/extract-variables', () => HttpResponse.json({ version: 'v1', extracted_values: { memory: 'extracted' }, warnings: [], json_schema: {}, variable_definitions: [], current_compose: remote, rendered_compose: remote })),
    http.post('*/api/templates/1/preview', () => HttpResponse.json({ rendered_yaml: 'rendered authored parameters' })),
    http.post('*/api/servers/alpha/check-conversion', () => HttpResponse.json({ version, requires_rebuild: true })),
    http.post('*/api/servers/alpha/convert-to-template', async ({ request }) => { submissions.push(await request.json() as Record<string, unknown>); return HttpResponse.json({ task_id: 'task', skipped_rebuild: false }) }),
  )
  show(); await edit()
  fireEvent.click(screen.getByRole('button', { name: '模板有更新' }))
  fireEvent.click(await screen.findByRole('button', { name: '下一步' }))
  const dialog = await screen.findByRole('dialog', { name: '更新模板配置' })
  const variables = await within(dialog).findByRole('textbox', { name: '模板参数' })
  fireEvent.change(variables, { target: { value: 'authored variables' } })
  remote = 'new remote'; version = 'v2'
  await act(async () => { await client.invalidateQueries({ queryKey: queryKeys.compose.detail('alpha') }) })
  await screen.findByText('在线配置已变更')
  fireEvent.click(screen.getByRole('button', { name: '下一步' }))
  await screen.findByText('在线配置已变更')
  expect(submissions).toHaveLength(0)
  await acceptCompared()
  expect((screen.getByRole('textbox', { name: '模板参数' }) as HTMLInputElement).value).toBe('authored variables')
  fireEvent.click(screen.getByRole('button', { name: '下一步' }))
  fireEvent.click(await screen.findByRole('button', { name: '确认更新并重建' }))
  await waitFor(() => expect(submissions).toEqual([{ template_id: 1, variable_values: { memory: 'authored variables' }, expected_version: 'v2' }]))
})

it.each([false, true])('accepts only its successful task version and preserves newer edits (template=%s)', async mode => {
  templateMode = mode
  const operation = { operation_id: 'operation', kind: 'server_rebuild', state: 'running', legacy_id: 'task', resources: [{ kind: 'server', server_id: 'alpha', generation: 1, path: '' }], data_changed: false, failure_code: null }
  server.use(http.get('*/api/operations', () => HttpResponse.json([operation])))
  show(true); const editor = await edit(); await submit()
  await screen.findByText('应用中')
  fireEvent.change(editor, { target: { value: 'next draft' } })
  remote = 'local draft'; version = 'v2'; operation.state = 'succeeded'
  server.use(http.get('*/api/tasks/task', () => HttpResponse.json({ task_id: 'task', task_type: 'server_rebuild', status: 'completed', created_at: '2026-09-25T12:00:00Z', result: { version: 'v2' } })))
  await act(async () => { await client.refetchQueries({ queryKey: queryKeys.operations.all }) })
  await waitFor(() => expect(toast.success).toHaveBeenCalledWith('服务器配置更新完成'))
  expect(editor.value).toBe('next draft')
  expect(screen.queryByText('在线配置已变更')).toBeNull()

  remote = 'other user v3'; version = 'v3'; operation.operation_id = 'another-operation'
  await act(async () => { await client.refetchQueries({ queryKey: queryKeys.operations.all }) })
  await screen.findByText('在线配置已变更')
  expect(editor.value).toBe('next draft')
  fireEvent.click(screen.getByRole('button', { name: '比较并解决冲突' }))
  await screen.findByRole('button', { name: '接受此版本为新基准' })
  const text = screen.getAllByLabelText('比较结果').map(element => element.textContent).join('\n')
  expect(text).toContain('local draft'); expect(text).toContain('other user v3'); expect(text).toContain('next draft')
})

it('does not accept a newer remote revision when its own successful result arrives later', async () => {
  const resultReady = deferred<void>()
  const operation = { operation_id: 'operation', kind: 'server_rebuild', state: 'running', legacy_id: 'task', resources: [{ kind: 'server', server_id: 'alpha', generation: 1, path: '' }], data_changed: false, failure_code: null }
  server.use(http.get('*/api/operations', () => HttpResponse.json([operation])))
  show(true); const editor = await edit(); await submit()
  await screen.findByText('应用中')
  remote = 'external v3'; version = 'v3'; operation.state = 'succeeded'
  server.use(http.get('*/api/tasks/task', async () => {
    await resultReady.promise
    return HttpResponse.json({ task_id: 'task', task_type: 'server_rebuild', status: 'completed', created_at: '2026-09-25T12:00:00Z', result: { version: 'v2' } })
  }))
  await act(async () => { await client.refetchQueries({ queryKey: queryKeys.operations.all }) })
  await waitFor(() => expect(client.getQueryData<{ version: string }>(queryKeys.compose.detail('alpha'))?.version).toBe('v3'))
  resultReady.resolve()
  await waitFor(() => expect(toast.success).toHaveBeenCalledWith('服务器配置更新完成'))
  await screen.findByText('在线配置已变更')
  expect(editor.value).toBe('local draft')
  expect((screen.getByRole('button', { name: '提交并重建' }) as HTMLButtonElement).disabled).toBe(true)
})

it('shows comparison refresh failures inside the dialog and requires a successful retry', async () => {
  templateMode = true
  show(); const editor = await edit()
  remote = 'changed'; version = 'v2'
  fireEvent.click(screen.getByRole('button', { name: '提交并重建' }))
  fireEvent.click(await screen.findByRole('button', { name: '比较并解决冲突' }))
  const dialog = await screen.findByRole('dialog', { name: '比较配置并确认提交基准' })
  server.use(http.get('*/api/servers/alpha/template-config', () => HttpResponse.json({ detail: '暂时不可用' }, { status: 503 })))
  fireEvent.click(within(dialog).getByRole('button', { name: '刷新比较' }))
  await within(dialog).findByText('读取在线配置失败，草稿已保留。请重试比较。')
  expect((within(dialog).getByRole('button', { name: '接受此版本为新基准' }) as HTMLButtonElement).disabled).toBe(true)
  expect(editor.value).toBe('local draft')
  server.use(http.get('*/api/servers/alpha/template-config', () => HttpResponse.json(template())))
  fireEvent.click(within(dialog).getByRole('button', { name: '刷新比较' }))
  await waitFor(() => expect((within(dialog).getByRole('button', { name: '接受此版本为新基准' }) as HTMLButtonElement).disabled).toBe(false))
})
