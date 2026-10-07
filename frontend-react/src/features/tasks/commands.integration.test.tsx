import { act, renderHook, waitFor } from '@testing-library/react'
import { afterAll, afterEach, beforeAll, expect, it } from 'vitest'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { createTestClient } from '@/test/http'
import { createOperationFeed } from '@/test/operations'
import { TestProviders } from '@/test/TestProviders'
import { OperationObserver } from '@/app/operations/OperationObserver'
import { queryKeys } from '@/shared/http/api'
import { useCancelTask } from './commands'

const server = setupServer()
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterAll(() => server.close())
afterEach(() => server.resetHandlers())

it('synchronizes terminal cancellation immediately after the cancel command', async () => {
  const client = createTestClient(), feed = createOperationFeed(1)
  server.use(feed.handler, http.post('*/api/tasks/restore/cancel', () => {
    feed.publish({ operation_id: 'restore', kind: 'snapshot_restore', state: 'cancelled', data_changed: true, updated_at: '2026-10-07T00:00:00Z', ended_at: '2026-10-07T00:00:00Z', resources: [{ kind: 'files', server_id: 'alpha', generation: 1, path: 'world' }] })
    feed.setActiveCount(0)
    return HttpResponse.json({})
  }))
  const view = renderHook(useCancelTask, { wrapper: ({ children }) => <TestProviders client={client}><OperationObserver sessionId="owner" />{children}</TestProviders> })
  await waitFor(() => expect(client.getQueryData(queryKeys.operations.session('owner'))).toBeTruthy())
  const files = queryKeys.files.list('alpha', '/world')
  client.setQueryData(files, [])
  await act(async () => { await view.result.current.mutateAsync('restore') })
  await waitFor(() => expect(client.getQueryState(files)?.isInvalidated).toBe(true))
  expect(client.getQueryData(queryKeys.operations.checkpoint('owner'))).toEqual({ cursor: '1:1', active_count: 0 })
  client.clear()
})
