import { cleanup, render, screen } from '@testing-library/react'
import { afterAll, afterEach, beforeAll, beforeEach, expect, it, vi } from 'vitest'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { TooltipProvider } from '@/shared/ui/tooltip'
import { createTestClient } from '@/test/http'
import { TestProviders } from '@/test/TestProviders'
import type { BackgroundTask, BackgroundTaskResponse } from '@/features/tasks/contracts'
import { useDownloadStore, type DownloadTask } from '@/features/tasks/downloadStore'
import { taskQueryKeys } from '@/features/tasks/queries'
import BackgroundTaskList from './BackgroundTaskList'
import DownloadTaskList from './DownloadTaskList'

const server = setupServer()
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
  const cached = client.getQueriesData<{ tasks: BackgroundTask[] }>({ queryKey: taskQueryKeys.all })[0][1]
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
