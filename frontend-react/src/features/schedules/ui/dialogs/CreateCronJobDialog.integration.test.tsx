import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterAll, afterEach, beforeAll, beforeEach, expect, it, vi } from 'vitest'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { createTestClient } from '@/test/http'
import { TestProviders } from '@/test/TestProviders'
import CreateCronJobDialog from './CreateCronJobDialog'

const server = setupServer()
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterAll(() => server.close())
let client: ReturnType<typeof createTestClient>
let writes: unknown[]
beforeEach(() => {
  client = createTestClient(); writes = []
  vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} })
  server.use(
    http.get('*/api/cron/registered', () => HttpResponse.json([
      { identifier: 'backup', description: '备份任务', is_system: false },
      { identifier: 'restart_server', description: '服务器重启', is_system: false },
    ])),
    http.post('*/api/cron/', async ({ request }) => { writes.push(await request.json()); return HttpResponse.json({ cronjob_id: 'created' }) }),
    http.put('*/api/cron/fixture', async ({ request }) => { writes.push(await request.json()); return HttpResponse.json({ message: '已更新' }) }),
  )
})
afterEach(() => { client.clear(); server.resetHandlers(); vi.unstubAllGlobals() })

async function selectOption(trigger: HTMLElement, name: string) {
  await waitFor(() => expect(trigger.hasAttribute('disabled')).toBe(false))
  fireEvent.click(trigger)
  const option = (await screen.findAllByRole('option', { name }))[0]
  fireEvent.pointerDown(option); fireEvent.click(option)
}

function show(isEdit = false) {
  return render(<TestProviders client={client}><CreateCronJobDialog open onCancel={() => {}} isEdit={isEdit} cronjobId={isEdit ? 'fixture' : undefined} /></TestProviders>)
}

it.each([false, true])('submits zero-valued minute, hour, weekday and optional second through HTTP (edit=%s)', async isEdit => {
  server.use(http.get('*/api/cron/fixture', () => HttpResponse.json({ cronjob_id: 'fixture', identifier: 'backup', name: '测试任务', cron: '10 2 * * 1', params: { enable_forget: false, prune: true } })))
  show(isEdit)
  if (!isEdit) {
    await selectOption(screen.getAllByRole('combobox')[0], '备份任务')
    fireEvent.click(screen.getByRole('checkbox', { name: '备份后清理旧快照' }))
  } else await screen.findByRole('checkbox', { name: '备份后清理旧快照' })
  fireEvent.change(screen.getByLabelText('任务名称'), { target: { value: '测试任务' } })
  for (const label of ['分钟 (0-59)', '小时 (0-23)', '秒 (0-59)']) {
    const field = screen.getByText(label).parentElement!.parentElement!
    if (within(field).queryByRole('spinbutton') === null) await selectOption(within(field).getByRole('combobox'), '指定值')
    fireEvent.change(within(field).getByRole('spinbutton'), { target: { value: '5' } })
    fireEvent.change(within(field).getByRole('spinbutton'), { target: { value: '0' } })
  }
  const weekday = screen.getByText('星期 (0-7)').parentElement!.parentElement!
  if (within(weekday).getAllByRole('combobox').length === 1) await selectOption(within(weekday).getByRole('combobox'), '指定值')
  await selectOption(within(weekday).getAllByRole('combobox')[1], '周五')
  await selectOption(within(weekday).getAllByRole('combobox')[1], '周日')
  expect(writes).toEqual([])
  fireEvent.click(screen.getByRole('button', { name: isEdit ? '更新任务' : '创建任务' }))
  await waitFor(() => expect(writes).toEqual([{ identifier: 'backup', params: { enable_forget: false, prune: true }, cron: '0 0 * * 0', name: '测试任务', second: '0' }]))
})

it('edits a managed restart target independently of the display name', async () => {
  server.use(http.get('*/api/cron/fixture', () => HttpResponse.json({ cronjob_id: 'fixture', identifier: 'restart_server', name: '凌晨维护窗口', cron: '40 3 * * *', params: { server_id: 'alpha' }, managed_purpose: 'restart' })))
  show(true)
  const target = await screen.findByRole('textbox', { name: '服务器 ID' })
  expect((target as HTMLInputElement).value).toBe('alpha')
  expect((screen.getByLabelText('任务名称') as HTMLInputElement).value).toBe('凌晨维护窗口')
  fireEvent.change(target, { target: { value: 'beta' } })
  fireEvent.click(screen.getByRole('button', { name: '更新任务' }))
  await waitFor(() => expect(writes).toEqual([{ identifier: 'restart_server', params: { server_id: 'beta' }, cron: '40 3 * * *', name: '凌晨维护窗口' }]))
})

it('clears backup parameters when switching to restart and waits for a complete target', async () => {
  show()
  await selectOption(screen.getAllByRole('combobox')[0], '备份任务')
  fireEvent.change(screen.getByLabelText('保留最近快照数'), { target: { value: '3' } })
  fireEvent.change(screen.getByLabelText('服务器 ID'), { target: { value: 'old-target' } })
  await selectOption(screen.getAllByRole('combobox')[0], '服务器重启')
  expect(screen.queryByLabelText('保留最近快照数')).toBeNull()
  expect((screen.getByLabelText('服务器 ID') as HTMLInputElement).value).toBe('')
  expect(screen.getByRole('button', { name: '创建任务' }).hasAttribute('disabled')).toBe(true)
  fireEvent.change(screen.getByLabelText('任务名称'), { target: { value: '重启测试' } })
  fireEvent.change(screen.getByLabelText('服务器 ID'), { target: { value: 'new-target' } })
  fireEvent.click(screen.getByRole('button', { name: '创建任务' }))
  await waitFor(() => expect(writes).toEqual([{ identifier: 'restart_server', params: { server_id: 'new-target' }, cron: '0 0 * * *', name: '重启测试' }]))
})

it('validates backup retention while preserving zero and false in the submitted parameters', async () => {
  show()
  await selectOption(screen.getAllByRole('combobox')[0], '备份任务')
  expect(screen.getByRole('button', { name: '创建任务' }).hasAttribute('disabled')).toBe(true)
  fireEvent.change(screen.getByLabelText('任务名称'), { target: { value: '备份测试' } })
  fireEvent.change(screen.getByLabelText('保留最近快照数'), { target: { value: '0' } })
  fireEvent.click(screen.getByRole('checkbox', { name: '清理未使用的数据块' }))
  fireEvent.click(screen.getByRole('button', { name: '创建任务' }))
  await waitFor(() => expect(writes).toEqual([{ identifier: 'backup', params: { enable_forget: true, prune: false, keep_last: 0 }, cron: '0 0 * * *', name: '备份测试' }]))
})

it.each([false, true])('requires explicit save after Enter in a parameter field (edit=%s)', async isEdit => {
  server.use(http.get('*/api/cron/fixture', () => HttpResponse.json({ cronjob_id: 'fixture', identifier: 'restart_server', name: '参数任务', cron: '0 0 * * *', params: { server_id: 'old' } })))
  show(isEdit)
  if (!isEdit) await selectOption(screen.getAllByRole('combobox')[0], '服务器重启')
  else await screen.findByLabelText('服务器 ID')
  fireEvent.change(screen.getByLabelText('任务名称'), { target: { value: '参数任务' } })
  const target = screen.getByLabelText('服务器 ID')
  fireEvent.change(target, { target: { value: 'typed' } })
  fireEvent.keyDown(target, { key: 'Enter' })
  expect(writes).toEqual([])
  fireEvent.change(target, { target: { value: 'explicit-save' } })
  fireEvent.click(screen.getByRole('button', { name: isEdit ? '更新任务' : '创建任务' }))
  await waitFor(() => expect(writes).toEqual([{ identifier: 'restart_server', params: { server_id: 'explicit-save' }, cron: '0 0 * * *', name: '参数任务' }]))
})
