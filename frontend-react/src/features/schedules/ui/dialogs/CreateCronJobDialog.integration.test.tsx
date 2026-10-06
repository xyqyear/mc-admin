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
beforeEach(() => {
  client = createTestClient()
  vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} })
})
afterEach(() => { client.clear(); server.resetHandlers(); vi.unstubAllGlobals() })

async function selectOption(trigger: HTMLElement, name: string) {
  await waitFor(() => expect(trigger.hasAttribute('disabled')).toBe(false))
  fireEvent.click(trigger)
  const option = await screen.findByRole('option', { name })
  fireEvent.pointerDown(option)
  fireEvent.click(option)
}

it.each([false, true])('submits accepted zero-valued minute, hour, weekday and optional second through HTTP (edit=%s)', async (isEdit) => {
  const writes: unknown[] = []
  server.use(
    http.get('*/api/cron/registered', () => HttpResponse.json([{ identifier: 'fixture_job', description: '测试任务', is_system: false, parameter_schema: { type: 'object', properties: {} } }])),
    http.get('*/api/cron/fixture', () => HttpResponse.json({ cronjob_id: 'fixture', identifier: 'fixture_job', name: '测试任务', cron: '5 5 * * 5', second: '5', params: {}, status: 'active' })),
    http.post('*/api/cron/', async ({ request }) => { writes.push(await request.json()); return HttpResponse.json({ message: '已创建', cronjob_id: 'fixture' }) }),
    http.put('*/api/cron/fixture', async ({ request }) => { writes.push(await request.json()); return HttpResponse.json({ message: '已更新' }) }),
  )
  render(<TestProviders client={client}><CreateCronJobDialog open onCancel={() => {}} isEdit={isEdit} cronjobId={isEdit ? 'fixture' : undefined} /></TestProviders>)
  await waitFor(() => expect(screen.getAllByRole('combobox')[0].hasAttribute('disabled')).toBe(isEdit))
  if (!isEdit) {
    await selectOption(screen.getAllByRole('combobox')[0], '测试任务')
    fireEvent.change(screen.getByLabelText('任务名称'), { target: { value: '测试任务' } })
  } else {
    await waitFor(() => expect((screen.getByLabelText('任务名称') as HTMLInputElement).value).toBe('测试任务'))
  }
  for (const label of ['分钟 (0-59)', '小时 (0-23)', '秒 (0-59)']) {
    const field = screen.getByText(label).parentElement!.parentElement!
    if (within(field).queryByRole('spinbutton') === null) await selectOption(within(field).getByRole('combobox'), '指定值')
    fireEvent.change(within(field).getByRole('spinbutton'), { target: { value: '5' } })
    fireEvent.change(within(field).getByRole('spinbutton'), { target: { value: '0' } })
  }
  const weekday = screen.getByText('星期 (0-7)').parentElement!.parentElement!
  if (within(weekday).getAllByRole('combobox').length === 1) await selectOption(within(weekday).getByRole('combobox'), '指定值')
  await selectOption(within(weekday).getAllByRole('combobox')[1], '周五')
  fireEvent.click(within(weekday).getAllByRole('combobox')[1])
  const sunday = (await screen.findAllByRole('option', { name: '周日' }))[0]
  fireEvent.pointerDown(sunday)
  fireEvent.click(sunday)
  expect(writes).toEqual([])
  fireEvent.click(screen.getByRole('button', { name: isEdit ? '更新任务' : '创建任务' }))
  await waitFor(() => expect(writes).toEqual([{ identifier: 'fixture_job', params: {}, cron: '0 0 * * 0', name: '测试任务', second: '0' }]))
})

it('renders dynamic parameter types and validation and discards the previous job draft before creating', async () => {
  const writes: unknown[] = []
  server.use(
    http.get('*/api/cron/registered', () => HttpResponse.json([
      { identifier: 'old-job', description: '旧任务', parameter_schema: { type: 'object', properties: {
        count: { type: 'integer', title: '旧数量', default: 2, minimum: 1 }, note: { type: 'string', title: '旧备注', default: 'old' },
      } } },
      { identifier: 'new-job', description: '新任务', parameter_schema: { type: 'object', properties: {
        limit: { type: 'integer', title: '新数量', default: 3 }, note: { type: 'string', title: '新备注', default: 'fresh' },
        enabled: { type: 'boolean', title: '启用参数', default: true },
      } } },
    ])),
    http.post('*/api/cron/', async ({ request }) => { writes.push(await request.json()); return HttpResponse.json({ cronjob_id: 'created' }) }),
  )
  render(<TestProviders client={client}><CreateCronJobDialog open onCancel={() => {}} /></TestProviders>)
  await selectOption(screen.getAllByRole('combobox')[0], '旧任务')
  const count = await screen.findByLabelText('旧数量')
  expect((count as HTMLInputElement).value).toBe('2')
  fireEvent.change(count, { target: { value: '0' } })
  await screen.findByText('must be >= 1')
  fireEvent.change(screen.getByLabelText('旧备注'), { target: { value: 'authored old draft' } })
  await selectOption(screen.getAllByRole('combobox')[0], '新任务')
  expect(screen.queryByLabelText('旧数量')).toBeNull()
  expect((screen.getByLabelText('新备注') as HTMLInputElement).value).toBe('fresh')
  expect((screen.getByLabelText('新数量') as HTMLInputElement).value).toBe('3')
  expect(screen.getByRole('checkbox', { name: '启用参数' }).getAttribute('aria-checked')).toBe('true')
  fireEvent.change(screen.getByLabelText('新数量'), { target: { value: '5' } })
  fireEvent.click(screen.getByRole('checkbox', { name: '启用参数' }))
  fireEvent.change(screen.getByLabelText('任务名称'), { target: { value: '参数任务' } })
  expect(writes).toEqual([])
  fireEvent.click(screen.getByRole('button', { name: '创建任务' }))
  await waitFor(() => expect(writes).toEqual([{ identifier: 'new-job', params: { limit: 5, note: 'fresh', enabled: false }, cron: '0 0 * * *', name: '参数任务' }]))
})

it.each([false, true])('keeps an Enter-triggered parameter form submission from saving the outer job (edit=%s)', async isEdit => {
  const writes: unknown[] = []
  server.use(
    http.get('*/api/cron/registered', () => HttpResponse.json([{ identifier: 'fixture_job', description: '参数任务', parameter_schema: { type: 'object', properties: { note: { type: 'string', title: '备注' } } } }])),
    http.get('*/api/cron/fixture', () => HttpResponse.json({ cronjob_id: 'fixture', identifier: 'fixture_job', name: '参数任务', cron: '0 0 * * *', params: { note: 'old' }, status: 'active' })),
    http.post('*/api/cron/', async ({ request }) => { writes.push(await request.json()); return HttpResponse.json({ cronjob_id: 'created' }) }),
    http.put('*/api/cron/fixture', async ({ request }) => { writes.push(await request.json()); return HttpResponse.json({ message: '已更新' }) }),
  )
  render(<TestProviders client={client}><CreateCronJobDialog open onCancel={() => {}} isEdit={isEdit} cronjobId={isEdit ? 'fixture' : undefined} /></TestProviders>)
  if (!isEdit) await selectOption(screen.getAllByRole('combobox')[0], '参数任务')
  else await screen.findByLabelText('备注')
  fireEvent.change(screen.getByLabelText('任务名称'), { target: { value: '参数任务' } })
  const note = screen.getByLabelText('备注')
  fireEvent.change(note, { target: { value: 'typed' } })
  fireEvent.keyDown(note, { key: 'Enter' })
  // JSDOM does not perform the browser's implicit Enter submission.
  fireEvent.submit(note.closest('form')!)
  fireEvent.change(note, { target: { value: 'explicit-save' } })
  fireEvent.click(screen.getByRole('button', { name: isEdit ? '更新任务' : '创建任务' }))
  await waitFor(() => expect(writes).toEqual([{ identifier: 'fixture_job', params: { note: 'explicit-save' }, cron: '0 0 * * *', name: '参数任务' }]))
})
