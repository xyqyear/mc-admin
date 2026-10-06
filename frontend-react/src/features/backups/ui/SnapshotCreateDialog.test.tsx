import { useState } from 'react'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterAll, afterEach, beforeAll, expect, it } from 'vitest'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { createTestClient } from '@/test/http'
import { TestProviders } from '@/test/TestProviders'
import { useCreateSnapshot } from '../commands'
import { SnapshotCreateDialog } from './SnapshotCreateDialog'

const server = setupServer()
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterAll(() => server.close())
afterEach(() => server.resetHandlers())

function Create() {
  const creation = useCreateSnapshot()
  const [open, setOpen] = useState(true)
  return <SnapshotCreateDialog creation={creation} request={open ? { scope: { kind: 'paths', server_id: 'alpha', paths: ['plugins'] }, label: '插件目录' } : null} onClose={() => setOpen(false)} />
}

it('shows real creation stages, keeps closing blocked across failed reads and closes only at completion', async () => {
  const client = createTestClient()
  let completed = false
  let failedReads = 0
  let submissions = 0
  let reads = 0
  server.use(
    http.post('*/api/snapshots', () => { submissions++; return HttpResponse.json({ task_id: 'backup', skipped_paths: [] }, { status: 202 }) }),
    http.get('*/api/tasks/backup', () => {
      reads++
      if (reads > 1 && !completed) { failedReads++; return HttpResponse.json({}, { status: 503 }) }
      return HttpResponse.json({ task_id: 'backup', status: completed ? 'completed' : 'running', progress: null, message: '正在读取文件并创建快照', result: completed ? { snapshot: { short_id: 'created' } } : null })
    }),
  )
  const view = render(<TestProviders client={client}><Create /></TestProviders>)
  try {
    fireEvent.click(screen.getByRole('button', { name: '创建快照' }))
    await screen.findByText('正在读取文件并创建快照')
    expect(screen.queryByText('0%')).toBeNull()
    expect((screen.getByRole('button', { name: '取消' }) as HTMLButtonElement).disabled).toBe(true)
    await waitFor(() => expect(failedReads).toBeGreaterThan(0), { timeout: 3000 })
    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' })
    expect(screen.getByRole('dialog', { name: '确认创建快照' })).toBeTruthy()
    expect((screen.getByRole('button', { name: '创建快照' }) as HTMLButtonElement).disabled).toBe(true)
    expect(submissions).toBe(1)
    completed = true
    await waitFor(() => expect(screen.queryByRole('dialog', { name: '确认创建快照' })).toBeNull(), { timeout: 3000 })
  } finally { completed = true; view.unmount(); client.clear() }
})

it('retains an existing snapshot after note failure and retries only its note', async () => {
  const client = createTestClient()
  const creates: unknown[] = []
  const notes: unknown[] = []
  const snapshotId = 'a'.repeat(64)
  server.use(
    http.post('*/api/snapshots', async ({ request }) => {
      creates.push(await request.json())
      return HttpResponse.json({ task_id: 'backup', skipped_paths: [] }, { status: 202 })
    }),
    http.get('*/api/tasks/backup', () => HttpResponse.json({ task_id: 'backup', status: 'completed', message: '快照已创建，但备注保存失败', result: {
      snapshot: { id: snapshotId, short_id: 'aaaaaaaa', note: '' }, note_warning: '快照已创建，但备注保存失败', skipped_paths: [],
    } })),
    http.put(`*/api/snapshots/${snapshotId}/note`, async ({ request }) => {
      notes.push(await request.json())
      return HttpResponse.json({ id: snapshotId, note: '升级前的中文备注' })
    }),
  )
  const view = render(<TestProviders client={client}><Create /></TestProviders>)
  try {
    fireEvent.change(screen.getByLabelText('快照备注（可选）'), { target: { value: '升级前的中文备注' } })
    fireEvent.click(screen.getByRole('button', { name: '创建快照' }))
    await screen.findByText('快照已创建：aaaaaaaa')
    expect(screen.queryByRole('button', { name: '创建快照' })).toBeNull()
    expect(creates).toEqual([{ scope: { kind: 'paths', server_id: 'alpha', paths: ['plugins'] }, note: '升级前的中文备注' }])
    fireEvent.click(screen.getByRole('button', { name: '仅重试保存备注' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    expect(notes).toEqual([{ note: '升级前的中文备注' }])
    expect(creates).toHaveLength(1)
  } finally { view.unmount(); client.clear() }
})

it('accepts 500 Unicode characters and rejects longer notes before submission', async () => {
  const client = createTestClient()
  const view = render(<TestProviders client={client}><Create /></TestProviders>)
  try {
    fireEvent.change(screen.getByLabelText('快照备注（可选）'), { target: { value: '😀'.repeat(500) } })
    expect(screen.getByText('500/500 字')).toBeTruthy()
    expect((screen.getByRole('button', { name: '创建快照' }) as HTMLButtonElement).disabled).toBe(false)
    fireEvent.change(screen.getByLabelText('快照备注（可选）'), { target: { value: '字'.repeat(501) } })
    expect((screen.getByRole('button', { name: '创建快照' }) as HTMLButtonElement).disabled).toBe(true)
  } finally { view.unmount(); client.clear() }
})
