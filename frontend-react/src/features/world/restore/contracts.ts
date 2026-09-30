import type { RestorationSelection } from '@/features/backups/contracts'

export type PreviewEventType =
  | 'start'
  | 'stage'
  | 'merge_region'
  | 'render_progress'
  | 'ready'
  | 'error'

export interface PreviewEvent {
  event_type: PreviewEventType
  message?: string
  session_id?: string
  percent?: number
}


export interface PreviewRequest {
  source_snapshot_id: string
  selection: RestorationSelection
}

export interface RestorePreviewRequest {
  sourceSnapshotId: string
  selection: RestorationSelection
}
