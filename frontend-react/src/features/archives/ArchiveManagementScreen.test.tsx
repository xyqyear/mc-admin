import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterAll, afterEach, beforeAll, expect, it, vi } from 'vitest'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { createTestClient } from '@/test/http'
import { TestProviders } from '@/test/TestProviders'
import ArchiveManagementScreen from './ArchiveManagementScreen'

vi.mock('./ui/ArchiveUploadDialog', () => ({ default: () => null }))
vi.mock('./ui/ArchiveRenameDialog', () => ({ default: () => null }))
const server = setupServer()
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterAll(() => server.close())
afterEach(() => server.resetHandlers())

it('deletes exactly the checked archive paths and retains unselected files', async () => {
  const client = createTestClient()
  let files = ['z.zip', 'a.zip', 'keep.zip'].map(name => ({ name, path: `/${name}`, type: 'file', size: 10, modified_at: '2026-10-01T00:00:00Z' }))
  const deleted: string[] = []
  server.use(
    http.get('*/api/archive', () => HttpResponse.json({ items: files })),
    http.delete('*/api/archive', ({ request }) => {
      const path = new URL(request.url).searchParams.get('path')!
      deleted.push(path)
      files = files.filter(file => file.path !== path)
      return HttpResponse.json({ task_id: 'delete-archive' }, { status: 202 })
    }),
    http.get('*/api/tasks/delete-archive', () => HttpResponse.json({ task_id: 'delete-archive', task_type: 'archive_delete', name: '删除', status: 'completed', created_at: '2026-10-01T00:00:00Z', result: { success: true } })),
  )
  const view = render(<TestProviders client={client}><ArchiveManagementScreen /></TestProviders>)
  await screen.findByText('z.zip')
  fireEvent.click(screen.getByRole('checkbox', { name: '选择 z.zip' }))
  fireEvent.click(screen.getByRole('checkbox', { name: '选择 a.zip' }))
  fireEvent.click(screen.getByRole('button', { name: '批量删除 (2)' }))
  fireEvent.click(await screen.findByRole('button', { name: '确定' }))
  await waitFor(() => expect(deleted).toHaveLength(2))
  expect(deleted.sort()).toEqual(['/a.zip', '/z.zip'])
  await waitFor(() => expect(screen.queryByText('z.zip')).toBeNull())
  expect(screen.getByText('keep.zip')).toBeTruthy()
  view.unmount()
  client.clear()
})
