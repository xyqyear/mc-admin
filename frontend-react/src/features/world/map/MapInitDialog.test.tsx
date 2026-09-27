import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import MapInitDialog from '@/features/world/map/MapInitDialog'
import { api } from '@/shared/http/api'
import { createTestClient, httpResponse } from '@/test/http'
import { TestProviders } from '@/test/TestProviders'

const original = api.defaults.adapter
afterEach(() => { api.defaults.adapter = original })

it('keeps initialization blocked through a read failure and 100% progress until the task settles', async () => {
  let status = 'running'
  let unavailable = false
  let reads = 0
  let submissions = 0
  api.defaults.adapter = async config => {
    if (config.url === '/tasks') return httpResponse(config, { tasks: [], total: 0 })
    if (config.url?.endsWith('/initialize')) {
      submissions++
      return httpResponse(config, { task_id: 'initialization' }, 202)
    }
    reads++
    return httpResponse(config, {
      task_id: 'initialization', task_type: 'map_initialize', status, name: '初始化地图',
      created_at: new Date().toISOString(), progress: 100, message: '正在整理缓存', cancellable: true,
      result: { stages: { client: { stage: 'client', phase: 'done', percent: 100 }, palette: { stage: 'palette', phase: 'done', percent: 100 } } },
    }, unavailable ? 503 : 200)
  }
  const onComplete = vi.fn()
  const onClose = vi.fn()
  const client = createTestClient()
  render(<TestProviders client={client}><MapInitDialog open serverId="server" onClose={onClose} onComplete={onComplete} /></TestProviders>)
  await waitFor(() => expect(reads).toBe(1))
  expect(screen.queryByRole('button', { name: /close/i })).toBeNull()
  fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' })
  expect(onClose).not.toHaveBeenCalled()
  unavailable = true
  await waitFor(() => expect(reads).toBeGreaterThan(1), { timeout: 2500 })
  expect(onComplete).not.toHaveBeenCalled()
  expect(screen.queryByRole('button', { name: /close/i })).toBeNull()
  unavailable = false
  status = 'completed'
  await waitFor(() => expect(onComplete).toHaveBeenCalledOnce(), { timeout: 2500 })
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
