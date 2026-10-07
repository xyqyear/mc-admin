import { act, renderHook, waitFor } from '@testing-library/react'
import { afterAll, afterEach, beforeAll, beforeEach, expect, it } from 'vitest'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { createTestClient } from '@/test/http'
import { createOperationFeed } from '@/test/operations'
import { TestProviders } from '@/test/TestProviders'
import { OperationObserver } from '@/app/operations/OperationObserver'
import { queryKeys } from '@/shared/http/api'
import { useCreateArchive, useRenameItem } from './commands'

const server = setupServer()
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterAll(() => server.close())
let client: ReturnType<typeof createTestClient>
beforeEach(() => { client = createTestClient() })
afterEach(() => { client.clear(); server.resetHandlers() })
const wrapper = ({ children }: { children: React.ReactNode }) => <TestProviders client={client}><OperationObserver sessionId="owner" />{children}</TestProviders>

it('immediately discovers an accepted compression task from an idle observer without claiming completion', async () => {
  const feed = createOperationFeed()
  server.use(feed.handler, http.post('*/api/archive/compress', () => {
    feed.publish({ operation_id: 'compression', kind: 'archive_create', state: 'queued', data_changed: false, updated_at: '2026-10-07T00:00:00Z', ended_at: null, resources: [{ kind: 'files', server_id: 'alpha', generation: 1, path: 'world' }] })
    feed.setActiveCount(1)
    return HttpResponse.json({ task_id: 'compression' }, { status: 202 })
  }))
  const view = renderHook(useCreateArchive, { wrapper })
  await waitFor(() => expect(client.getQueryData(queryKeys.operations.session('owner'))).toEqual({ cursor: '1:0', active_count: 0 }))
  const archive = queryKeys.archive.files('/')
  client.setQueryData(archive, [])
  await act(async () => { expect(await view.result.current.mutateAsync({ server_id: 'alpha', paths: ['/world'] })).toEqual({ task_id: 'compression' }) })
  await waitFor(() => expect(client.getQueryData(queryKeys.operations.checkpoint('owner'))).toEqual({ cursor: '1:1', active_count: 1 }))
  expect(client.getQueryState(archive)?.isInvalidated).toBe(false)
})

it('immediately synchronizes a committed archive rename after an idle command', async () => {
  const feed = createOperationFeed()
  server.use(feed.handler, http.post('*/api/archive/rename', () => {
    feed.publish({ operation_id: 'rename', kind: 'archive_write', state: 'succeeded', data_changed: true, updated_at: '2026-10-07T00:00:00Z', ended_at: '2026-10-07T00:00:00Z', resources: [{ kind: 'archive', server_id: null, generation: null, path: 'old.zip' }] })
    return HttpResponse.json({ message: '已重命名' })
  }))
  const view = renderHook(useRenameItem, { wrapper })
  await waitFor(() => expect(client.getQueryData(queryKeys.operations.session('owner'))).toBeTruthy())
  const otherFolder = queryKeys.archive.files('/other')
  client.setQueryData(otherFolder, [])
  await act(async () => { await view.result.current.mutateAsync({ old_path: '/old.zip', new_name: 'new.zip' }) })
  await waitFor(() => expect(client.getQueryState(otherFolder)?.isInvalidated).toBe(true))
  expect(client.getQueryData(queryKeys.operations.checkpoint('owner'))).toEqual({ cursor: '1:1', active_count: 0 })
})
