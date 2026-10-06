import { useState } from 'react'
import type { Snapshot } from '../contracts'
import { useUpdateSnapshotNote } from '../commands'
import { Button } from '@/shared/ui/button'
import { Label } from '@/shared/ui/label'
import { Textarea } from '@/shared/ui/textarea'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/shared/ui/dialog'

export function SnapshotNoteDialog({ snapshot, onClose }: { snapshot: Snapshot | null; onClose: () => void }) {
  return snapshot ? <NoteEditor key={snapshot.id} snapshot={snapshot} onClose={onClose} /> : null
}

function NoteEditor({ snapshot, onClose }: { snapshot: Snapshot; onClose: () => void }) {
  const [note, setNote] = useState(snapshot.note ?? '')
  const update = useUpdateSnapshotNote()
  const length = Array.from(note).length
  return <Dialog open onOpenChange={open => { if (!open && !update.isPending) onClose() }}>
    <DialogContent>
      <DialogHeader>
        <DialogTitle>编辑快照备注</DialogTitle>
        <DialogDescription>快照 {snapshot.short_id} 的备注随应用数据库保存。</DialogDescription>
      </DialogHeader>
      <div className="space-y-2">
        <Label htmlFor="snapshot-edit-note">快照备注</Label>
        <Textarea id="snapshot-edit-note" value={note} disabled={update.isPending} onChange={event => setNote(event.target.value)} />
        <p className={length > 500 ? 'text-sm text-destructive' : 'text-sm text-muted-foreground'}>{length}/500 字</p>
      </div>
      <DialogFooter>
        <Button variant="outline" disabled={update.isPending} onClick={onClose}>取消</Button>
        <Button disabled={update.isPending || length > 500} onClick={() => update.mutate({ snapshotId: snapshot.id, note }, { onSuccess: onClose })}>保存备注</Button>
      </DialogFooter>
    </DialogContent>
  </Dialog>
}
