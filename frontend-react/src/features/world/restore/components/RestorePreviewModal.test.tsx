import { act, render, screen } from '@testing-library/react'
import { expect, it, vi } from 'vitest'

import { RestorePreviewModal } from '@/features/world/restore/components/RestorePreviewModal'
import type { EventStreamOptions } from '@/shared/http/eventStream'
import type { PreviewEvent } from '@/features/world/restore/contracts'

const stream = vi.hoisted(() => ({ options: null as EventStreamOptions<PreviewEvent> | null }))
vi.mock('@/shared/hooks/useEventStream', () => ({
  useEventStream: (options: EventStreamOptions<PreviewEvent>) => { stream.options = options },
}))
vi.mock('@/features/world/restore/commands', () => ({
  useWorldRestoreMutations: () => ({
    useEndPreview: () => ({ mutate: vi.fn() }),
    useHeartbeatPreview: () => ({ mutate: vi.fn() }),
  }),
}))

it('ends preview waiting when the stream closes before ready', async () => {
  render(<RestorePreviewModal serverId="server" onClose={vi.fn()} request={{
    sourceSnapshotId: 'snapshot',
    selection: { type: 'regions', region_dir_relpath: 'world/region', regions: [[0, 0]] },
  }} />)
  await act(async () => { stream.options?.onEvent({ event_type: 'start', session_id: 'session' }) })
  await act(async () => { stream.options?.onClose?.() })
  expect(screen.getByText('连接中断，请重新生成预览')).toBeTruthy()
  expect(screen.getByRole('button', { name: /close/i })).toBeTruthy()
})
