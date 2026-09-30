import type { RestorationSelection } from '@/features/backups/contracts'

export interface RestorePreviewRequest {
  sourceSnapshotId: string
  selection: RestorationSelection
}
