import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterAll, afterEach, beforeAll, expect, it, vi } from 'vitest'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { createTestClient } from '@/test/http'
import { TestProviders } from '@/test/TestProviders'
import PopulateProgressDialog from '@/features/archives/ui/PopulateProgressDialog'

const server = setupServer()
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterAll(() => server.close())
afterEach(() => server.resetHandlers())
it('allows the progress dialog to close without cancelling its independent task', async () => {
  const client = createTestClient()
  const onClose = vi.fn()
  let cancellations = 0
  server.use(
    http.get('*/api/tasks/populate', () => HttpResponse.json({ task_id: 'populate', task_type: 'archive_extract', status: 'running', name: 'populate', progress: 20, message: '正在解压', server_id: 'alpha', created_at: new Date().toISOString(), cancellable: true })),
    http.post('*/api/tasks/populate/cancel', () => { cancellations++; return HttpResponse.json({}) }),
  )
  const view = render(<TestProviders client={client}><PopulateProgressDialog serverId="alpha" taskId="populate" open onClose={onClose} onComplete={() => {}} /></TestProviders>)
  await screen.findByText('正在解压')
  fireEvent.click(screen.getByRole('button', { name: /close/i }))
  await waitFor(() => expect(onClose).toHaveBeenCalledOnce())
  view.unmount()
  expect(cancellations).toBe(0)
  client.clear()
})
