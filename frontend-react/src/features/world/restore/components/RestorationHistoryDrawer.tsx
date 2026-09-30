import { Eye } from 'lucide-react'
import { useState } from 'react'
import { RestorationHistoryDialog } from '@/features/backups/ui/RestorationHistoryDialog'
import { Button } from '@/shared/ui/button'
import { RestorePreviewModal, type RestorePreviewRequest } from './RestorePreviewModal'

interface RestorationHistoryDrawerProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  serverId: string
  serverStopped: boolean
}

export function RestorationHistoryDrawer({ open, onOpenChange, serverId, serverStopped }: RestorationHistoryDrawerProps) {
  const [preview, setPreview] = useState<RestorePreviewRequest | null>(null)
  return <>
    <RestorationHistoryDialog open={open} onClose={() => onOpenChange(false)} scope={{ kind: 'server', server_id: serverId }} serverStopped={serverStopped}
      renderActions={row => row.scope?.kind === 'world' && row.safety_snapshot_id && row.rollback_available && ['regions', 'chunks'].includes(row.scope.selection.type)
        ? <Button size="sm" variant="outline" onClick={() => {
          if (row.scope?.kind === 'world' && row.safety_snapshot_id) setPreview({ sourceSnapshotId: row.safety_snapshot_id, selection: row.scope.selection })
        }}><Eye className="mr-1 h-3.5 w-3.5" />预览</Button> : null} />
    <RestorePreviewModal serverId={serverId} request={preview} onClose={() => setPreview(null)} />
  </>
}

export default RestorationHistoryDrawer
