import { act, render, screen } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'

import MapInitDialog from './MapInitDialog'
import type { EventStreamOptions } from '@/utils/eventStream'
import type { InitEvent } from '@/types/MapTypes'

const stream = vi.hoisted(() => ({ options: null as EventStreamOptions<InitEvent> | null }))
vi.mock('@/utils/eventStream', () => ({
  readEventStream: vi.fn(async (options: EventStreamOptions<InitEvent>) => { stream.options = options }),
}))

beforeEach(() => { stream.options = null })

it('shows an error and allows closing when initialization ends without completion', async () => {
  const onComplete = vi.fn()
  render(<MapInitDialog open serverId="server" onClose={vi.fn()} onComplete={onComplete} />)
  await act(async () => { stream.options?.onClose?.() })
  expect(screen.getByText(/连接中断，请重试地图初始化/)).toBeTruthy()
  expect(screen.getByRole('button', { name: /close/i })).toBeTruthy()
  expect(onComplete).not.toHaveBeenCalled()
})
