import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterAll, afterEach, beforeAll, expect, it } from 'vitest'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { createTaskEvents, taskResponse, taskEventsUnavailable } from '@/test/taskEvents'
import { createTestClient, deferred } from '@/test/http'
import { createOperationFeed } from '@/test/operations'
import { TestProviders } from '@/test/TestProviders'
import { OperationObserver } from '@/app/operations/OperationObserver'
import { queryKeys } from '@/shared/http/api'
import SelfCheckScreen from './SelfCheckScreen'

const server = setupServer(taskEventsUnavailable)
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterAll(() => server.close())
afterEach(() => server.resetHandlers())

it('discovers accepted self-check work after leaving the submitting screen', async () => {
  const client = createTestClient(), feed = createOperationFeed()
  const submitted = deferred<void>(), release = deferred<void>()
  server.use(feed.handler,
    http.get('*/api/self-check/status', () => HttpResponse.json({ catalog: [], runs: [], total: 0, retention_runs_keep_days: 14 })),
    http.get('*/api/tasks', () => HttpResponse.json({ tasks: [] })),
    http.post('*/api/self-check/run', async () => {
      submitted.resolve(); await release.promise
      feed.setActiveCount(1)
      feed.publish({ operation_id: 'self-check', kind: 'self_check', state: 'queued', data_changed: false, updated_at: '2026-10-07T00:00:00Z', ended_at: null, resources: [] })
      return HttpResponse.json({ task_id: 'self-check' }, { status: 202 })
    }),
  )
  render(<TestProviders client={client}><OperationObserver sessionId="owner" /></TestProviders>)
  await waitFor(() => expect(client.getQueryData(queryKeys.operations.checkpoint('owner'))).toBeTruthy())
  const view = render(<TestProviders client={client}><SelfCheckScreen /></TestProviders>)
  fireEvent.click(await screen.findByRole('button', { name: '立即自检' }))
  await submitted.promise
  view.unmount()
  await act(async () => { release.resolve() })
  await waitFor(() => expect(client.getQueryData(queryKeys.operations.checkpoint('owner'))).toEqual({ cursor: '1:1', active_count: 1 }))
  client.clear()
})

it('streams findings and check counters while retaining its guard until a settled result', async () => {
  const { createTaskEvents, taskResponse } = await import('@/test/taskEvents')
  const client = createTestClient()
  const feed = createTaskEvents()
  const catalog = [{ check_id: 'first', category: 'system', title: '第一项检查', description: '', enabled: true },
    { check_id: 'second', category: 'system', title: '第二项检查', description: '', enabled: true }]
  let reads = 0
  const task = taskResponse('self-check', { task_type: 'self_check' })
  server.use(feed.handler,
    http.get('*/api/self-check/status', () => HttpResponse.json({ catalog, runs: [], total: 0, retention_runs_keep_days: 14 })),
    http.get('*/api/tasks', () => HttpResponse.json({ tasks: [] })),
    http.post('*/api/self-check/run', () => { feed.upsert(task); return HttpResponse.json({ task_id: task.task_id }, { status: 202 }) }),
    http.get('*/api/tasks/self-check', () => { reads++; return HttpResponse.json(task) }),
  )
  const view = render(<TestProviders client={client}><SelfCheckScreen /></TestProviders>)
  const runButton = await screen.findByRole('button', { name: '立即自检' }) as HTMLButtonElement
  fireEvent.click(runButton)
  await waitFor(() => expect(feed.activeConnections).toBe(1))
  const finding = { check_id: 'first', category: 'system', severity: 'warning', status: 'warning', title: '第一项检查',
    message: '检测到需要处理的配置', evidence: {}, remediation: [], created_at: '2026-10-18T00:00:00Z' }
  act(() => feed.upsert({ ...task, progress: 50, progress_details: { kind: 'self_check', findings: [finding], checking: true,
    check_id: 'second', started_at: '2026-10-18T00:00:00Z', completed_checks: 1, total_checks: 2 } }))
  await screen.findByText('检测到需要处理的配置')
  await screen.findByText('第二项检查')
  await screen.findByText(/已完成 1\/2 项/)
  const initialReads = reads
  expect(runButton.disabled).toBe(true)
  act(() => feed.close())
  await screen.findByText(/正在重新连接任务进度/)
  expect(runButton.disabled).toBe(true)
  await waitFor(() => expect(feed.connections).toBe(2), { timeout: 2500 })
  act(() => feed.upsert({ ...task, status: 'completed', progress: 100, result: {
    id: 'run', trigger: 'manual', scope: 'full', status: 'warning', started_at: '2026-10-18T00:00:00Z', finished_at: '2026-10-18T00:01:00Z',
    duration_ms: 60000, findings: [finding], summary: { total: 1, passed: 0, skipped: 0, info: 0, warning: 1, critical: 0, failed: 0, status: 'warning' },
  } }))
  await waitFor(() => expect(runButton.disabled).toBe(false))
  expect(reads).toBe(initialReads)
  expect(screen.getByText('检测到需要处理的配置')).toBeTruthy()
  view.unmount()
  client.clear()
})

it('shows truncated live findings and retries the same completed result after a read failure', async () => {
  const client = createTestClient()
  const feed = createTaskEvents()
  const task = taskResponse('self-check-retry', { task_type: 'self_check' })
  const finding = { check_id: 'first', category: 'system', severity: 'warning', status: 'warning', title: '端口检查',
    message: '检查结果完整保留', evidence: {}, remediation: [], created_at: '2026-10-18T00:00:00Z' }
  const result = { id: 'run', trigger: 'manual', scope: 'full', status: 'warning', started_at: finding.created_at,
    finished_at: finding.created_at, duration_ms: 1, findings: [finding],
    summary: { total: 1, passed: 0, skipped: 0, info: 0, warning: 1, critical: 0, failed: 0, status: 'warning' } }
  let readable = false
  let submissions = 0
  server.use(feed.handler,
    http.get('*/api/self-check/status', () => HttpResponse.json({ catalog: [], runs: [], total: 0, retention_runs_keep_days: 14 })),
    http.get('*/api/tasks', () => HttpResponse.json({ tasks: [] })),
    http.post('*/api/self-check/run', () => {
      submissions++
      feed.upsert(task)
      return HttpResponse.json({ task_id: task.task_id }, { status: 202 })
    }),
    http.get('*/api/tasks/self-check-retry', () => readable
      ? HttpResponse.json({ ...task, status: 'completed', result })
      : HttpResponse.json({ detail: '结果暂时不可读' }, { status: 503 })),
  )
  const view = render(<TestProviders client={client}><SelfCheckScreen /></TestProviders>)
  const run = await screen.findByRole('button', { name: '立即自检' }) as HTMLButtonElement
  fireEvent.click(run)
  await waitFor(() => expect(submissions).toBe(1))
  act(() => feed.upsert({ ...task, progress_details: { kind: 'self_check', findings: [], findings_total: 100,
    findings_truncated: true, completed_checks: 1, total_checks: 2 } }))
  await screen.findByText(/已产生 100 条检查结果/)
  act(() => feed.upsert({ ...task, status: 'completed', result_included: false }))
  const retry = await screen.findByRole('button', { name: '重试读取结果' })
  expect(run.disabled).toBe(true)
  readable = true
  fireEvent.click(retry)
  await screen.findByText('检查结果完整保留')
  await waitFor(() => expect(run.disabled).toBe(false))
  expect(screen.queryByText(/已产生 100 条检查结果/)).toBeNull()
  expect(submissions).toBe(1)
  view.unmount()
  client.clear()
})
