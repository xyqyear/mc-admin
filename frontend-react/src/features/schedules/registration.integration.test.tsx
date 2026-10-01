import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterAll, afterEach, beforeAll, beforeEach, expect, it } from 'vitest'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import CronManagementScreen from '@/features/schedules/CronManagementScreen'
import { ServerRestartScheduleCard } from '@/features/servers/ui/ServerRestartScheduleCard'
import { useServerQueries } from '@/features/servers/queries'
import type { CronJob } from '@/features/schedules/contracts'
import { createTestClient } from '@/test/http'
import { TestProviders } from '@/test/TestProviders'
import { Route, Routes } from 'react-router'

const server = setupServer()
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterAll(() => server.close())
let client: ReturnType<typeof createTestClient>
let job: CronJob
let resumes = 0
let nextRunReads = 0
beforeEach(() => {
  client = createTestClient(); resumes = 0; nextRunReads = 0
  job = { cronjob_id: 'restart-alpha', identifier: 'restart', name: 'Alpha 每日重启', cron: '0 0 * * *', params: { server_id: 'alpha' }, execution_count: 0, is_system: false, status: 'active', created_at: '2026-09-25T00:00:00Z', updated_at: '2026-09-25T00:00:00Z', registration_status: 'failed', registration_error: '调度器注册失败，请重新启用任务' }
  server.use(
    http.get('*/api/cron/registered', () => HttpResponse.json([])),
    http.get('*/api/cron/', () => HttpResponse.json([job])),
    http.get('*/api/servers/alpha/restart-schedule', () => HttpResponse.json({ ...job, server_id: 'alpha', scheduled_time: '00:00', next_run_time: '2099-09-26T00:00:00Z' })),
    http.get('*/api/cron/restart-alpha/next-run-time', () => { nextRunReads++; return HttpResponse.json({ cronjob_id: job.cronjob_id, next_run_time: '2099-09-26T00:00:00Z' }) }),
    http.post('*/api/cron/restart-alpha/resume', () => { resumes++; job = { ...job, registration_status: 'registered', registration_error: null }; return HttpResponse.json({ message: '任务已恢复' }) }),
  )
})
afterEach(() => { client.clear(); server.resetHandlers() })
function ScheduleCard() {
  const { useRestartSchedule } = useServerQueries()
  const schedule = useRestartSchedule('alpha')
  return <ServerRestartScheduleCard serverId="alpha" restartSchedule={schedule.data} isLoading={schedule.isLoading} error={schedule.error} />
}

it('keeps an active failed schedule visible, retries registration, and refreshes the server card', async () => {
  render(<TestProviders client={client}><CronManagementScreen /><ScheduleCard /></TestProviders>)
  await screen.findByText('Alpha 每日重启')
  await waitFor(() => expect(screen.getAllByText('注册失败，暂未调度')).toHaveLength(2))
  expect(screen.queryByText('运行中')).toBeNull()
  expect(screen.queryByText('下次执行:')).toBeNull()
  expect(nextRunReads).toBe(0)
  fireEvent.click(screen.getByTitle('重新启用'))
  fireEvent.click(await screen.findByRole('button', { name: '确认启用' }))
  await waitFor(() => expect(screen.getAllByText('调度已注册')).toHaveLength(2))
  expect(resumes).toBe(1)
  expect(screen.queryByTitle('重新启用')).toBeNull()
  await screen.findByText('下次执行:')
})

it('keeps old responses readable without claiming a registration failure', async () => {
  delete job.registration_status; delete job.registration_error
  render(<TestProviders client={client}><ScheduleCard /></TestProviders>)
  await screen.findByText('已启用')
  expect(screen.queryByText('注册失败，暂未调度')).toBeNull()
  await screen.findByText('下次执行:')
})

it('creates a managed server restart schedule and opens its details from the card', async () => {
  let created = false
  server.use(
    http.get('*/api/servers/alpha/restart-schedule', () => HttpResponse.json(created ? { ...job, server_id: 'alpha', scheduled_time: '00:00' } : null)),
    http.post('*/api/servers/alpha/restart-schedule', () => {
      created = true
      return HttpResponse.json({ ...job, server_id: 'alpha', scheduled_time: '00:00' })
    }),
    http.get('*/api/cron/restart-alpha', () => HttpResponse.json(job)),
    http.get('*/api/cron/restart-alpha/executions', () => HttpResponse.json([])),
  )
  render(<TestProviders client={client} route="/servers/alpha"><Routes>
    <Route path="/servers/alpha" element={<ScheduleCard />} />
    <Route path="/cron" element={<CronManagementScreen />} />
  </Routes></TestProviders>)
  await screen.findByText('未配置重启计划')
  fireEvent.click(screen.getByRole('button', { name: '配置计划' }))
  expect(created).toBe(false)
  fireEvent.click(await screen.findByRole('button', { name: '创建重启计划' }))
  await screen.findByText('00:00')
  expect(created).toBe(true)
  fireEvent.click(screen.getByRole('button', { name: '管理' }))
  await screen.findByRole('dialog')
  await screen.findByText('restart-alpha')
})
