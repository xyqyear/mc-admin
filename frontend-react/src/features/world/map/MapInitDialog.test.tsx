import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterAll, afterEach, beforeAll, expect, it, vi } from 'vitest'
import { setupServer } from 'msw/node'
import { taskEventsUnavailable, createTaskEvents, taskResponse } from '@/test/taskEvents'
import MapInitDialog from '@/features/world/map/MapInitDialog'
import { api } from '@/shared/http/api'
import { createTestClient, httpResponse } from '@/test/http'
import { TestProviders } from '@/test/TestProviders'

const original = api.defaults.adapter
const server = setupServer(taskEventsUnavailable)
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterAll(() => server.close())
afterEach(() => { api.defaults.adapter = original })

it('shows streamed stages and remains blocked through disconnect and running 100% until settlement', async () => {
  let reads = 0
  let submissions = 0
  const feed = createTaskEvents()
  const stages = [
    { stage: 'client', phase: 'done', percent: 100, cached: true },
    { stage: 'palette', phase: 'resolving', percent: 35, message: '正在解析方块颜色' },
  ]
  const task = taskResponse('initialization', { task_type: 'map_initialize', progress: 67.5,
    progress_details: { kind: 'map', stages },
  })
  server.use(feed.handler)
  api.defaults.adapter = async config => {
    if (config.url === '/tasks') return httpResponse(config, { tasks: [], total: 0 })
    if (config.url?.endsWith('/initialize')) {
      submissions++
      feed.upsert(task)
      return httpResponse(config, { task_id: 'initialization' }, 202)
    }
    reads++
    return httpResponse(config, task)
  }
  const onComplete = vi.fn()
  const onClose = vi.fn()
  const client = createTestClient()
  render(<TestProviders client={client}><MapInitDialog open force serverId="server" onClose={onClose} onComplete={onComplete} /></TestProviders>)
  await screen.findByText('正在解析方块颜色')
  expect(screen.getByText('35%')).toBeTruthy()
  expect(screen.getByText('100%（已缓存）')).toBeTruthy()
  const initialReads = reads
  const done = { ...task, progress: 100, progress_details: { kind: 'map', stages: [stages[0], { stage: 'palette', phase: 'done', percent: 100 }] } }
  act(() => feed.upsert(done))
  await screen.findByText('100%')
  expect(screen.queryByRole('button', { name: /close/i })).toBeNull()
  fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' })
  expect(onClose).not.toHaveBeenCalled()
  act(() => feed.close())
  await screen.findByText('正在重新连接任务进度，后台任务仍在继续')
  expect(onComplete).not.toHaveBeenCalled()
  expect(screen.queryByRole('button', { name: /close/i })).toBeNull()
  await waitFor(() => expect(feed.connections).toBe(2), { timeout: 2500 })
  expect(reads).toBe(initialReads)
  act(() => feed.upsert({ ...done, status: 'completed', result: { stages: {} } }))
  await waitFor(() => expect(onComplete).toHaveBeenCalledOnce())
  expect(reads).toBe(initialReads)
  expect(submissions).toBe(1)
  client.clear()
})

it('reattaches an existing task and makes a confirmed failure dismissible', async () => {
  const task = { task_id: 'existing', task_type: 'map_initialize', server_id: 'server', name: '初始化地图', created_at: new Date().toISOString(), progress: null, cancellable: true }
  const requests: string[] = []
  api.defaults.adapter = async config => {
    requests.push(config.url!)
    return httpResponse(config, config.url === '/tasks'
      ? { tasks: [{ ...task, status: 'running' }], total: 1 }
      : { ...task, status: 'failed', error: '调色板生成失败' })
  }
  const client = createTestClient()
  const onComplete = vi.fn()
  render(<TestProviders client={client}><MapInitDialog open serverId="server" onClose={vi.fn()} onComplete={onComplete} /></TestProviders>)
  await screen.findByText(/调色板生成失败/)
  expect(screen.getByRole('button', { name: /close/i })).toBeTruthy()
  expect(requests).toEqual(['/tasks', '/tasks/existing'])
  expect(onComplete).not.toHaveBeenCalled()
  client.clear()
})
