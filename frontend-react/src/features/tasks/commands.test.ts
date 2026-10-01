import { afterAll, afterEach, beforeAll, expect, it } from 'vitest'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { createTestClient } from '@/test/http'
import { waitForTaskResult } from './commands'

const server = setupServer()
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterAll(() => server.close())
afterEach(() => server.resetHandlers())

it('reconnects after transient failure and returns the retained result', async () => {
  const client = createTestClient()
  let reads = 0
  server.use(http.get('*/api/tasks/retained', () => ++reads === 1
    ? HttpResponse.json({ detail: 'unavailable' }, { status: 503 })
    : HttpResponse.json({ task_id: 'retained', status: 'completed', created_at: '2026-10-01T00:00:00Z', result: { snapshot: { short_id: 'backup' } } })))
  await expect(waitForTaskResult(client, { task_id: 'retained' })).resolves.toEqual({ snapshot: { short_id: 'backup' } })
  expect(reads).toBe(2)
  client.clear()
})

it('reports expired task history instead of retrying a permanent 404 forever', async () => {
  const client = createTestClient()
  let reads = 0
  server.use(http.get('*/api/tasks/expired', () => { reads++; return HttpResponse.json({ detail: '不存在' }, { status: 404 }) }))
  await expect(waitForTaskResult(client, { task_id: 'expired' })).rejects.toThrow('任务记录已过期或不存在')
  expect(reads).toBe(1)
  client.clear()
})
