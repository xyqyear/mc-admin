import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterAll, afterEach, beforeAll, beforeEach, expect, it, vi } from 'vitest'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { createTaskEvents, taskEventsUnavailable, taskResponse } from '@/test/taskEvents'
import { TooltipProvider } from '@/shared/ui/tooltip'
import { createTestClient } from '@/test/http'
import { TestProviders } from '@/test/TestProviders'
import type { BackgroundTask, BackgroundTaskResponse } from '@/features/tasks/contracts'
import { useDownloadStore, type DownloadTask } from '@/features/tasks/downloadStore'
import { taskQueryKeys } from '@/features/tasks/queries'
import BackgroundTaskList from './BackgroundTaskList'
import DownloadTaskList from './DownloadTaskList'

const server = setupServer(taskEventsUnavailable)
const now = new Date('2026-10-17T08:00:00Z').getTime()
const minute = 60_000
let client: ReturnType<typeof createTestClient>

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterAll(() => server.close())
beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(now)
  client = createTestClient()
  useDownloadStore.setState({ tasks: [] })
  localStorage.clear()
})
afterEach(() => {
  cleanup()
  client.clear()
  useDownloadStore.setState({ tasks: [] })
  localStorage.clear()
  server.resetHandlers()
  vi.useRealTimers()
})

function backgroundTask(name: string, status: BackgroundTaskResponse['status'], createdMinutes: number, endedMinutes?: number): BackgroundTaskResponse {
  return {
    task_id: name, task_type: 'self_check', name, status, progress: 50,
    message: '', server_id: null, cancellable: true,
    created_at: new Date(now - createdMinutes * minute).toISOString(),
    ended_at: endedMinutes === undefined ? undefined : new Date(now - endedMinutes * minute).toISOString(),
  }
}

function downloadTask(fileName: string, status: DownloadTask['status'], startedMinutes: number, endedMinutes?: number): DownloadTask {
  return {
    id: fileName, fileName, status, progress: 50,
    startTime: now - startedMinutes * minute,
    endTime: endedMinutes === undefined ? undefined : now - endedMinutes * minute,
  }
}

it('shows newest background tasks first in each group without changing query order or recent filtering', async () => {
  const tasks = [
    backgroundTask('后台-旧进行', 'running', 40),
    backgroundTask('后台-旧完成', 'completed', 50, 1),
    backgroundTask('后台-过期', 'cancelled', 60, 31),
    backgroundTask('后台-新进行', 'pending', 20),
    backgroundTask('后台-新完成', 'failed', 10, 2),
  ]
  server.use(http.get('*/api/tasks', () => HttpResponse.json({ tasks, total: tasks.length })))

  render(<TestProviders client={client}><TooltipProvider><BackgroundTaskList /></TooltipProvider></TestProviders>)

  await screen.findByTitle('后台-新进行')
  expect(screen.getAllByTitle(/^后台-/).map(element => element.textContent)).toEqual([
    '后台-新进行', '后台-旧进行', '后台-新完成', '后台-旧完成',
  ])
  expect(screen.getByText('正在进行 (2)')).toBeTruthy()
  expect(screen.getByText('已完成 (2)')).toBeTruthy()
  expect(screen.queryByTitle('后台-过期')).toBeNull()
  const cached = client.getQueryData<{ tasks: BackgroundTask[] }>(taskQueryKeys.list())
  expect(cached?.tasks.map(task => task.name)).toEqual([
    '后台-旧进行', '后台-旧完成', '后台-过期', '后台-新进行', '后台-新完成',
  ])
})

it('shows newest downloads first in each group without changing stored order or recent filtering', () => {
  useDownloadStore.setState({ tasks: [
    downloadTask('下载-旧进行', 'downloading', 40),
    downloadTask('下载-旧完成', 'completed', 50, 1),
    downloadTask('下载-过期', 'cancelled', 60, 31),
    downloadTask('下载-新进行', 'downloading', 20),
    downloadTask('下载-新完成', 'error', 10, 2),
  ] })

  render(<TooltipProvider><DownloadTaskList /></TooltipProvider>)

  expect(screen.getAllByTitle(/^下载-/).map(element => element.textContent)).toEqual([
    '下载-新进行', '下载-旧进行', '下载-新完成', '下载-旧完成',
  ])
  expect(screen.getByText('正在下载 (2)')).toBeTruthy()
  expect(screen.getByText('已完成 (2)')).toBeTruthy()
  expect(screen.queryByTitle('下载-过期')).toBeNull()
  expect(useDownloadStore.getState().tasks.map(task => task.fileName)).toEqual([
    '下载-旧进行', '下载-旧完成', '下载-过期', '下载-新进行', '下载-新完成',
  ])
})


it('distinguishes an unavailable task list from an empty list and retries explicitly', async () => {
  let available = false
  server.use(http.get('*/api/tasks', () => available ? HttpResponse.json({ tasks: [], total: 0 }) : HttpResponse.json({ detail: '服务暂不可用' }, { status: 503 })))
  render(<TestProviders client={client}><TooltipProvider><BackgroundTaskList /></TooltipProvider></TestProviders>)
  expect((await screen.findByRole('alert')).textContent).toContain('无法读取后台任务')
  expect(screen.queryByText('暂无后台任务')).toBeNull()
  available = true
  fireEvent.click(screen.getByRole('button', { name: '重试连接' }))
  expect(await screen.findByText('暂无后台任务')).toBeTruthy()
})

it('shows stale task state during a stream interruption', async () => {
  const task = taskResponse('断线中的任务')
  const feed = createTaskEvents([task])
  server.use(feed.handler, http.get('*/api/tasks', () => HttpResponse.json({ tasks: [task], total: 1 })))
  render(<TestProviders client={client}><TooltipProvider><BackgroundTaskList /></TooltipProvider></TestProviders>)
  await screen.findByTitle('断线中的任务')
  feed.close()
  expect(await screen.findByText('任务连接已中断，显示的是上次收到的状态。')).toBeTruthy()
  expect(screen.getByTitle('断线中的任务')).toBeTruthy()
  expect(screen.getByRole('button', { name: '重试连接' })).toBeTruthy()
})

it('reads retained partial results on demand and retries the same result after a transient error', async () => {
  const errors = [{ server_id: '需检查的服务器', error: '目录仍被占用' }]
  const task = { ...taskResponse('partial-sync', { name: '同步部分失败', task_type: 'server_sync', status: 'completed' }), result_included: false }
  const feed = createTaskEvents([task])
  let available = false
  let reads = 0
  server.use(feed.handler, http.get('*/api/tasks', () => HttpResponse.json({ tasks: [task], total: 1 })),
    http.get(`*/api/tasks/${task.task_id}`, () => { reads++; return available ? HttpResponse.json({ ...task, result: { errors, applied: true } }) : HttpResponse.json({ detail: '结果暂不可读' }, { status: 503 }) }),
  )
  render(<TestProviders client={client}><TooltipProvider><BackgroundTaskList /></TooltipProvider></TestProviders>)
  fireEvent.click(await screen.findByTitle('同步部分失败'))
  expect(reads).toBe(0)
  fireEvent.click(await screen.findByRole('button', { name: '查看结果' }))
  const retry = await screen.findByRole('button', { name: '重试读取结果' })
  expect(screen.getByText('任务已结束，但完整结果读取失败。请重试读取，无需重新执行任务。')).toBeTruthy()
  available = true
  const before = reads
  fireEvent.click(retry)
  expect(await screen.findByText('逐项失败结果（1）')).toBeTruthy()
  expect(screen.getByText('需检查的服务器')).toBeTruthy()
  expect(screen.getByText('目录仍被占用')).toBeTruthy()
  expect(reads).toBe(before + 1)
})

it('reports cancellation failure and releases its action button for retry', async () => {
  const { toast } = await import('sonner')
  const showError = vi.spyOn(toast, 'error')
  const task = taskResponse('cancel-failure', { name: '不能取消的任务' })
  server.use(http.get('*/api/tasks', () => HttpResponse.json({ tasks: [task], total: 1 })), http.post(`*/api/tasks/${task.task_id}/cancel`, () => HttpResponse.json({ detail: '任务正在收尾' }, { status: 409 })))
  render(<TestProviders client={client}><TooltipProvider><BackgroundTaskList /></TooltipProvider></TestProviders>)
  fireEvent.click(await screen.findByRole('button', { name: '取消任务' }))
  await waitFor(() => expect(showError).toHaveBeenCalledWith(expect.stringContaining('取消任务失败')))
  expect((screen.getByRole('button', { name: '取消任务' }) as HTMLButtonElement).disabled).toBe(false)
})

it.each([
  ['移除任务', '移除任务失败'],
  ['清除', '清除任务失败'],
])('keeps %s pending and reports a failed command without erasing the task', async (label, errorPrefix) => {
  const { toast } = await import('sonner')
  const showError = vi.spyOn(toast, 'error')
  const task = taskResponse('retained-on-error', { name: '应保留的任务', status: 'completed' })
  let release!: () => void
  const gate = new Promise<void>(resolve => { release = resolve })
  server.use(http.get('*/api/tasks', () => HttpResponse.json({ tasks: [task], total: 1 })),
    http.delete('*/api/tasks/:id', async () => { await gate; return HttpResponse.json({ detail: '暂时无法修改记录' }, { status: 503 }) }),
    http.delete('*/api/tasks', async () => { await gate; return HttpResponse.json({ detail: '暂时无法修改记录' }, { status: 503 }) }),
  )
  render(<TestProviders client={client}><TooltipProvider><BackgroundTaskList /></TooltipProvider></TestProviders>)
  const action = await screen.findByRole('button', { name: label })
  fireEvent.click(action)
  await waitFor(() => expect((action as HTMLButtonElement).disabled).toBe(true))
  release()
  await waitFor(() => expect(showError).toHaveBeenCalledWith(expect.stringContaining(errorPrefix)))
  expect(screen.getByTitle('应保留的任务')).toBeTruthy()
  expect((action as HTMLButtonElement).disabled).toBe(false)
})
