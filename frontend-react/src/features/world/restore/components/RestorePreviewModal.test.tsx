import { fireEvent, render, screen } from '@testing-library/react'
import { expect, it, vi } from 'vitest'

import { RestorePreviewModal } from './RestorePreviewModal'

const preview = vi.hoisted(() => ({ active: true, taskId: 'prepare', result: null, progress: null, message: '正在提取快照中的地图数据', error: null, cancel: vi.fn(), cancelling: false }))
vi.mock('@/features/backups/commands', () => ({ useSnapshotPreview: () => preview }))

it('shows a real preparation phase and permits closing observation or explicitly stopping preparation', () => {
  const close = vi.fn()
  render(<RestorePreviewModal serverId="server" onClose={close} request={{ sourceSnapshotId: 'snapshot', selection: { type: 'regions', region_dir_relpath: 'world/region', regions: [[0, 0]] } }} />)
  expect(screen.getByText('正在提取快照中的地图数据')).toBeTruthy()
  expect(screen.queryByText('0%')).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: '停止准备' }))
  expect(preview.cancel).toHaveBeenCalledOnce()
  expect(close).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: /close/i }))
  expect(close).toHaveBeenCalledOnce()
  expect(preview.cancel).toHaveBeenCalledOnce()
})
