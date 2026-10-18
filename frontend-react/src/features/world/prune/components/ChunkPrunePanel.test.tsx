import { fireEvent, render, screen } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import { createTestClient } from '@/test/http'
import { TestProviders } from '@/test/TestProviders'
import ChunkPrunePanel, { type ChunkPrunePanelProps } from './ChunkPrunePanel'

it.each(['preview', 'apply'] as const)('shows pending %s work and keeps its cancellation reachable', kind => {
  const client = createTestClient()
  const onCancel = vi.fn()
  const props: ChunkPrunePanelProps = {
    thresholdValue: '30', thresholdUnit: 'seconds', thresholdSeconds: 30, mode: 'regions',
    previewStatus: kind === 'preview' ? 'pending' : 'idle', previewStarting: false,
    previewProgress: null, previewMessage: null, previewResult: null, previewError: null,
    applyStatus: kind === 'apply' ? 'pending' : 'idle', applyProgress: 0, applyMessage: null, applyResult: null, applyError: null,
    serverStopped: true, canPreview: false, canApply: false, cancellingPreview: false, cancellingApply: false,
    onThresholdValueChange: vi.fn(), onThresholdUnitChange: vi.fn(), onModeChange: vi.fn(), onPreview: vi.fn(),
    onCancelPreview: onCancel, onApply: vi.fn(), onCancelApply: onCancel,
  }
  const view = render(<TestProviders client={client}><ChunkPrunePanel {...props} /></TestProviders>)
  expect(screen.getByText('等待执行')).toBeTruthy()
  expect((screen.getByRole('spinbutton') as HTMLInputElement).disabled).toBe(true)
  expect((screen.getByRole('button', { name: /^预览$/ }) as HTMLButtonElement).disabled).toBe(true)
  const cancel = screen.getByRole('button', { name: kind === 'preview' ? /^取消$/ : /^取消删除$/ }) as HTMLButtonElement
  expect(cancel.disabled).toBe(false)
  fireEvent.click(cancel)
  expect(onCancel).toHaveBeenCalledOnce()
  view.unmount()
  client.clear()
})
