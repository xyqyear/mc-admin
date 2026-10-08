import { fireEvent, render, screen, within } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import type { SnapshotRestoreSource } from '@/features/backups/contracts'
import { TestProviders } from '@/test/TestProviders'
import { createTestClient } from '@/test/http'
import { SnapshotSelectionDialog } from './SnapshotSelectionDialog'

it('shows each source protection beside its actions and preserves the chosen source identity', () => {
  const sources: SnapshotRestoreSource[] = [
    { id: 'first', short_id: 'first', time: '2026-10-08T00:00:00Z', hostname: 'server', username: 'owner', paths: [], excludes: [], skipped_paths: ['world', 'mods'], skipped_count: 2 },
    { id: 'second', short_id: 'second', time: '2026-10-07T00:00:00Z', hostname: 'server', username: 'owner', paths: [], excludes: [], skipped_paths: ['world'], skipped_count: 1 },
  ]
  const restore = vi.fn()
  const preview = vi.fn()
  const client = createTestClient()
  render(<TestProviders client={client}><SnapshotSelectionDialog open onCancel={vi.fn()} snapshots={sources} loading={false} onRestore={restore} restoreLoading={false} filePath="所选文件" onPreview={preview} previewLoading={false} /></TestProviders>)
  const first = within(screen.getByText('first').closest('tr')!)
  const second = within(screen.getByText('second').closest('tr')!)
  expect(first.getByText('将跳过 2 个忽略路径，保留其当前内容。')).toBeTruthy()
  expect(first.getByText('mods')).toBeTruthy()
  expect(second.getByText('将跳过 1 个忽略路径，保留其当前内容。')).toBeTruthy()
  expect(second.queryByText('mods')).toBeNull()
  fireEvent.click(first.getByRole('button', { name: '预览' }))
  fireEvent.click(second.getByRole('button', { name: '恢复' }))
  expect(preview).toHaveBeenCalledWith('first')
  expect(restore).toHaveBeenCalledWith('second')
  client.clear()
})
