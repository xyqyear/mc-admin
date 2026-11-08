import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterAll, afterEach, beforeAll, beforeEach, expect, it, vi } from 'vitest'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { queryKeys } from '@/shared/http/api'
import { createTestClient } from '@/test/http'
import { TestProviders } from '@/test/TestProviders'
import WorldSettingsScreen from './WorldSettingsScreen'
import LogParserSettingsScreen from './LogParserSettingsScreen'
import DNSSettingsScreen from './DNSSettingsScreen'
import PlayerSettingsScreen from './PlayerSettingsScreen'

vi.mock('@/shared/editors/index', () => ({
  MonacoDiffEditor: ({ original, modified }: { original: string; modified: string }) => <div aria-label="比较结果">{original} → {modified}</div>,
  SimpleEditor: ({ value, onChange }: { value: string; onChange: (value: string) => void }) => <textarea aria-label="命令内容" value={value} onChange={event => onChange(event.target.value)} />,
}))

const server = setupServer()
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterAll(() => server.close())
let client: ReturnType<typeof createTestClient>
beforeEach(() => { client = createTestClient() })
afterEach(() => { client.clear(); server.resetHandlers() })
const show = (page: React.ReactNode) => render(<TestProviders client={client}>{page}</TestProviders>)
const worldDefaults = { region_stat_workers: 32, dimension_max_depth_from_world_root: 4, dimension_labels: { '.': '主世界' } }

async function confirmSave() {
  fireEvent.click(screen.getByRole('button', { name: '保存设置' }))
  fireEvent.click(await screen.findByRole('button', { name: '确认提交' }))
}

it('keeps authored values during comparison and saves zero and edited dimension names', async () => {
  let remote = { ...worldDefaults }
  const writes: unknown[] = []
  server.use(
    http.get('*/api/settings/world', () => HttpResponse.json(remote)),
    http.put('*/api/settings/world', async ({ request }) => { remote = await request.json() as typeof remote; writes.push(remote); return HttpResponse.json(remote) }),
  )
  show(<WorldSettingsScreen />)
  const depth = await screen.findByRole('spinbutton', { name: '维度扫描最大深度' })
  fireEvent.change(depth, { target: { value: '0' } })
  fireEvent.change(screen.getByRole('textbox', { name: '维度名称值 1' }), { target: { value: '我的世界' } })
  remote = { ...remote, region_stat_workers: 7 }
  fireEvent.click(screen.getByRole('button', { name: '差异对比' }))
  await waitFor(() => expect(screen.getByLabelText('比较结果').textContent).toContain('7'))
  fireEvent.click(screen.getByRole('button', { name: '取消' }))
  expect((depth as HTMLInputElement).value).toBe('0')
  await confirmSave()
  await waitFor(() => expect(writes).toEqual([{ region_stat_workers: 32, dimension_max_depth_from_world_root: 0, dimension_labels: { '.': '我的世界' } }]))
})

it('retains drafts after rejected saves and failed reloads, and resets only after confirmation', async () => {
  let failRead = false
  let resets = 0
  server.use(
    http.get('*/api/settings/world', () => failRead ? HttpResponse.json({ detail: '读取失败' }, { status: 503 }) : HttpResponse.json(worldDefaults)),
    http.put('*/api/settings/world', () => HttpResponse.json({ detail: '保存失败' }, { status: 400 })),
    http.post('*/api/settings/world/reset', () => { resets++; return HttpResponse.json(worldDefaults) }),
  )
  show(<WorldSettingsScreen />)
  const workers = await screen.findByRole('spinbutton', { name: '区域清单扫描线程数' })
  fireEvent.change(workers, { target: { value: '9' } })
  await confirmSave()
  await waitFor(() => expect(client.isMutating()).toBe(0))
  fireEvent.click(screen.getByRole('button', { name: '取消' }))
  failRead = true
  fireEvent.click(screen.getByRole('button', { name: '重新载入' }))
  fireEvent.click(screen.getByRole('button', { name: '确认' }))
  await waitFor(() => expect(screen.queryByRole('alertdialog')).toBeNull())
  expect((workers as HTMLInputElement).value).toBe('9')
  failRead = false
  fireEvent.click(screen.getByRole('button', { name: '重置默认' }))
  expect(resets).toBe(0)
  fireEvent.click(screen.getByRole('button', { name: '确认' }))
  await waitFor(() => expect((workers as HTMLInputElement).value).toBe('32'))
  expect(resets).toBe(1)
})

it('keeps failed initial reads unwritable and supports retry', async () => {
  let failed = true
  server.use(http.get('*/api/settings/world', () => failed ? HttpResponse.json({ detail: '读取失败' }, { status: 503 }) : HttpResponse.json(worldDefaults)))
  show(<WorldSettingsScreen />)
  await screen.findByText('配置加载失败')
  expect(screen.queryByRole('button', { name: '保存设置' })).toBeNull()
  expect(screen.queryByRole('spinbutton')).toBeNull()
  failed = false
  fireEvent.click(screen.getByRole('button', { name: '重试' }))
  await screen.findByRole('spinbutton', { name: '区域清单扫描线程数' })
})

it('edits parser rules as text and ordered lists without replacing an authored draft on refresh', async () => {
  let remote = { uuid_patterns: ['(name) (uuid)'], join_pattern: '(name)', leave_pattern: '(name)', chat_pattern: '(prefix) (name) (message)', server_stop_pattern: 'stop', achievement_patterns: ['(name) (achievement)'] }
  const writes: unknown[] = []
  server.use(
    http.get('*/api/settings/log-parser', () => HttpResponse.json(remote)),
    http.put('*/api/settings/log-parser', async ({ request }) => { const body = await request.json(); writes.push(body); return HttpResponse.json(body) }),
  )
  show(<LogParserSettingsScreen />)
  const join = await screen.findByRole('textbox', { name: '玩家加入解析规则' })
  const rule = String.raw`^joined (\w+)$`
  fireEvent.change(join, { target: { value: rule } })
  fireEvent.click(screen.getByRole('button', { name: '添加UUID 解析规则' }))
  fireEvent.change(screen.getByRole('textbox', { name: 'UUID 解析规则 2' }), { target: { value: '(player)=(uuid)' } })
  remote = { ...remote, join_pattern: 'remote (player)' }
  await act(async () => { await client.invalidateQueries({ queryKey: queryKeys.settings.detail('log-parser') }) })
  expect((join as HTMLTextAreaElement).value).toBe(rule)
  await confirmSave()
  await waitFor(() => expect(writes).toHaveLength(1))
  expect(writes[0]).toEqual({ ...remote, join_pattern: rule, uuid_patterns: ['(name) (uuid)', '(player)=(uuid)'] })
})

it('switches DNS providers and submits only the selected provider and authored address', async () => {
  const initial = { enabled: false, dns: { type: 'huawei', domain: 'example.test', ak: 'fixture', sk: 'fixture', region: 'cn-south-1' }, managed_sub_domain: 'mc', mc_router_base_url: 'http://localhost:26666', dns_ttl: 15, addresses: [] }
  const writes: unknown[] = []
  server.use(
    http.get('*/api/settings/dns', () => HttpResponse.json(initial)),
    http.put('*/api/settings/dns', async ({ request }) => { const body = await request.json(); writes.push(body); return HttpResponse.json(body) }),
    http.get('*/api/dns/enabled', () => HttpResponse.json({ enabled: false })),
  )
  show(<DNSSettingsScreen />)
  fireEvent.click(await screen.findByRole('combobox', { name: 'DNS 提供商' }))
  const option = await screen.findByRole('option', { name: 'DNSPod' })
  fireEvent.pointerDown(option); fireEvent.click(option)
  expect(screen.queryByLabelText('访问密钥 ID')).toBeNull()
  fireEvent.change(screen.getByLabelText('DNSPod API 标识'), { target: { value: 'pod-id' } })
  fireEvent.change(screen.getByLabelText('DNSPod API 密钥'), { target: { value: 'pod-key' } })
  fireEvent.click(screen.getByRole('button', { name: '添加地址' }))
  fireEvent.change(screen.getByLabelText('地址名称 1'), { target: { value: 'play' } })
  fireEvent.change(screen.getByLabelText('记录值 1'), { target: { value: '127.0.0.1' } })
  await confirmSave()
  await waitFor(() => expect(writes).toEqual([{ ...initial, dns: { type: 'dnspod', domain: 'example.test', id: 'pod-id', key: 'pod-key' }, addresses: [{ type: 'manual', name: 'play', record_type: 'A', value: '127.0.0.1', port: 25565 }] }]))
})

it('edits the player command in the code editor while retaining other settings', async () => {
  const initial = { heartbeat: { crash_threshold_minutes: 5, heartbeat_interval_seconds: 60 }, rcon_validation: { validation_interval_seconds: 60 }, skin_fetcher: { request_timeout_seconds: 10 }, query: { query_command: 'original', timeout: 0.25 }, ignored_name_prefixes: ['bot_'] }
  const writes: unknown[] = []
  server.use(
    http.get('*/api/settings/players', () => HttpResponse.json(initial)),
    http.put('*/api/settings/players', async ({ request }) => { const body = await request.json(); writes.push(body); return HttpResponse.json(body) }),
  )
  show(<PlayerSettingsScreen />)
  const group = await screen.findByRole('group', { name: 'Query 命令模板' })
  fireEvent.change(within(group).getByRole('textbox'), { target: { value: 'printf "hello"\nprintf "world"' } })
  await confirmSave()
  await waitFor(() => expect(writes).toEqual([{ ...initial, query: { ...initial.query, query_command: 'printf "hello"\nprintf "world"' } }]))
})
