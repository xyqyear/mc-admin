import { useState } from 'react'
import { type useCreateSnapshot, useUpdateSnapshotNote } from '../commands'
import type { Snapshot, SnapshotScope } from '../contracts'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogFooter } from '@/shared/ui/dialog'
import { Button } from '@/shared/ui/button'
import { SnapshotCreationStatus } from './SnapshotCreationStatus'
import { Label } from '@/shared/ui/label'
import { Textarea } from '@/shared/ui/textarea'
import { Alert, AlertDescription, AlertTitle } from '@/shared/ui/alert'

export function SnapshotCreateDialog({ request, creation, onClose }: {
  request: { scope: SnapshotScope; label: string } | null
  creation: ReturnType<typeof useCreateSnapshot>
  onClose: () => void
}) {
  if (!request) return null
  return <CreateSnapshotDialogContent key={JSON.stringify(request.scope)} request={request} creation={creation} onClose={onClose} />
}

function CreateSnapshotDialogContent({ request, creation, onClose }: {
  request: { scope: SnapshotScope; label: string }
  creation: ReturnType<typeof useCreateSnapshot>
  onClose: () => void
}) {
  const [note, setNote] = useState('')
  const [created, setCreated] = useState<Snapshot | null>(null)
  const updateNote = useUpdateSnapshotNote()
  const noteLength = Array.from(note).length
  const pending = creation.isPending || updateNote.isPending
  return <Dialog open onOpenChange={open => { if (!open && !pending) onClose() }}>
    <DialogContent>
      <DialogHeader>
        <DialogTitle>确认创建快照</DialogTitle>
        <DialogDescription>确定要为 {request.label} 创建快照吗？忽略目录会被跳过。</DialogDescription>
      </DialogHeader>
      {created && <Alert>
        <AlertTitle>快照已创建：{created.short_id}</AlertTitle>
        <AlertDescription>备注保存失败。可仅重试保存备注，已有快照将保留。</AlertDescription>
      </Alert>}
      <div className="space-y-2">
        <Label htmlFor="snapshot-create-note">快照备注（可选）</Label>
        <Textarea id="snapshot-create-note" value={note} disabled={pending} onChange={event => setNote(event.target.value)} placeholder="说明快照的用途或恢复前的状态" />
        <p className={noteLength > 500 ? 'text-sm text-destructive' : 'text-sm text-muted-foreground'}>{noteLength}/500 字</p>
      </div>
      <SnapshotCreationStatus pending={creation.isPending} task={creation.task} />
      <DialogFooter>
        <Button variant="outline" disabled={pending} onClick={onClose}>{created ? '关闭' : '取消'}</Button>
        {created ? <Button disabled={pending || noteLength > 500} onClick={() => updateNote.mutate({ snapshotId: created.id, note }, { onSuccess: onClose })}>仅重试保存备注</Button>
          : <Button disabled={pending || noteLength > 500} onClick={() => {
            creation.mutate({ scope: request.scope, note }, { onSuccess: result => {
              if (result.note_warning) setCreated(result.snapshot)
              else onClose()
            } })
          }}>创建快照</Button>}
      </DialogFooter>
    </DialogContent>
  </Dialog>
}
