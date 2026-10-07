import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterAll, afterEach, beforeAll, expect, it } from 'vitest'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { createTestClient, deferred } from '@/test/http'
import { createOperationFeed } from '@/test/operations'
import { TestProviders } from '@/test/TestProviders'
import { OperationObserver } from '@/app/operations/OperationObserver'
import { queryKeys } from '@/shared/http/api'
import SelfCheckScreen from './SelfCheckScreen'

const server = setupServer()
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
      feed.publish({ operation_id: 'self-check', kind: 'self_check', state: 'queued', data_changed: false, updated_at: '2026-10-07T00:00:00Z', ended_at: null, resources: [] })
      feed.setActiveCount(1)
      return HttpResponse.json({ task_id: 'self-check' }, { status: 202 })
    }),
  )
  render(<TestProviders client={client}><OperationObserver sessionId="owner" /></TestProviders>)
  await waitFor(() => expect(client.getQueryData(queryKeys.operations.session('owner'))).toBeTruthy())
  const view = render(<TestProviders client={client}><SelfCheckScreen /></TestProviders>)
  fireEvent.click(await screen.findByRole('button', { name: '立即自检' }))
  await submitted.promise
  view.unmount()
  await act(async () => { release.resolve() })
  await waitFor(() => expect(client.getQueryData(queryKeys.operations.checkpoint('owner'))).toEqual({ cursor: '1:1', active_count: 1 }))
  client.clear()
})
