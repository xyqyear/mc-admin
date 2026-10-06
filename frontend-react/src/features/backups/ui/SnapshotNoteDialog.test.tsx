import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterAll, afterEach, beforeAll, expect, it } from 'vitest'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { useState } from 'react'
import { createTestClient } from '@/test/http'
import { TestProviders } from '@/test/TestProviders'
import { queryKeys } from '@/shared/http/api'
import type { Snapshot } from '../contracts'
import { SnapshotNoteDialog } from './SnapshotNoteDialog'

const server = setupServer()
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterAll(() => server.close())
afterEach(() => server.resetHandlers())

const snapshot: Snapshot = { id: 'a'.repeat(64), short_id: 'aaaaaaaa', note: '升级前', time: '2026-10-06T00:00:00Z', paths: ['/data/config'], excludes: [], username: 'owner', hostname: 'server' }

function Edit() {
  const [open, setOpen] = useState(true)
  return <SnapshotNoteDialog snapshot={open ? snapshot : null} onClose={() => setOpen(false)} />
}

it('preserves an authored note after failure, saves the same identity, and invalidates lists and eligible sources', async () => {
  const client = createTestClient()
  client.setQueryData(queryKeys.snapshots.global(), [snapshot])
  client.setQueryData(queryKeys.snapshots.eligible({ kind: 'global' }), { snapshots: [snapshot] })
  const writes: unknown[] = []
  let available = false
  server.use(http.put(`*/api/snapshots/${snapshot.id}/note`, async ({ request }) => {
    writes.push(await request.json())
    return available ? HttpResponse.json({ ...snapshot, note: '升级后' }) : HttpResponse.json({ detail: '稍后重试' }, { status: 503 })
  }))
  const view = render(<TestProviders client={client}><Edit /></TestProviders>)
  try {
    fireEvent.change(screen.getByLabelText('快照备注'), { target: { value: '升级后' } })
    fireEvent.click(screen.getByRole('button', { name: '保存备注' }))
    await waitFor(() => expect(writes).toHaveLength(1))
    await waitFor(() => expect((screen.getByRole('button', { name: '保存备注' }) as HTMLButtonElement).disabled).toBe(false))
    expect((screen.getByLabelText('快照备注') as HTMLTextAreaElement).value).toBe('升级后')
    available = true
    fireEvent.click(screen.getByRole('button', { name: '保存备注' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    expect(writes).toEqual([{ note: '升级后' }, { note: '升级后' }])
    expect(client.getQueryState(queryKeys.snapshots.global())?.isInvalidated).toBe(true)
    expect(client.getQueryState(queryKeys.snapshots.eligible({ kind: 'global' }))?.isInvalidated).toBe(true)
  } finally { view.unmount(); client.clear() }
})
