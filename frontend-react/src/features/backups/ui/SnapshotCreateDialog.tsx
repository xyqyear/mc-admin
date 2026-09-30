import type { useCreateSnapshot } from '../commands'
import type { SnapshotScope } from '../contracts'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogFooter } from '@/shared/ui/dialog'
import { Button } from '@/shared/ui/button'
import { SnapshotCreationStatus } from './SnapshotCreationStatus'

export function SnapshotCreateDialog({ request, creation, onClose }: {
  request: { scope: SnapshotScope; label: string } | null
  creation: ReturnType<typeof useCreateSnapshot>
  onClose: () => void
}) {
  return <Dialog open={!!request} onOpenChange={open => { if (!open && !creation.isPending) onClose() }}>
    <DialogContent>
      <DialogHeader>
        <DialogTitle>确认创建快照</DialogTitle>
        <DialogDescription>确定要为 {request?.label} 创建快照吗？忽略目录会被跳过。</DialogDescription>
      </DialogHeader>
      <SnapshotCreationStatus pending={creation.isPending} task={creation.task} />
      <DialogFooter>
        <Button variant="outline" disabled={creation.isPending} onClick={onClose}>取消</Button>
        <Button disabled={creation.isPending} onClick={() => {
          if (request) creation.mutate(request.scope, { onSuccess: onClose })
        }}>创建快照</Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>
}
