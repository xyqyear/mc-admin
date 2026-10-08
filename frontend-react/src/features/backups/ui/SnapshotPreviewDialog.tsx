import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Button } from '@/shared/ui/button'
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from '@/shared/ui/dialog'
import { Spinner } from '@/shared/ui/spinner'
import { Progress } from '@/shared/ui/progress'
import { snapshotApi } from '../api'
import { useSnapshotPreview } from '../useSnapshotPreview'
import type { SnapshotPreviewRequest } from '../contracts'
import { SnapshotSkipNotice } from './SnapshotSkipNotice'

const labels = { updated: '更新', deleted: '删除', restored: '恢复' }

interface SnapshotPreviewDialogProps {
  request: SnapshotPreviewRequest | null
  onClose: () => void
  onRestore?: (previewId: string) => void
}

export function SnapshotPreviewDialog({ request, onClose, onRestore }: SnapshotPreviewDialogProps) {
  const state = useSnapshotPreview(request)
  const [cursors, setCursors] = useState([0])
  const id = state.result?.preview_id
  useEffect(() => { setCursors([0]) }, [id])
  const cursor = cursors.at(-1) ?? 0
  const actions = useQuery({
    queryKey: ['snapshot-preview', id, cursor],
    queryFn: () => snapshotApi.previewActions(id!, cursor),
    enabled: !!id,
  })
  const nextCursor = actions.data?.next_cursor

  return (
    <Dialog open={!!request} onOpenChange={open => { if (!open) onClose() }}>
      <DialogContent className="sm:max-w-200 max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>恢复预览</DialogTitle>
          <DialogDescription>
            预览不会修改文件。关闭准备中的预览只停止观察，任务会继续；也可明确停止准备。
          </DialogDescription>
        </DialogHeader>
        {state.active && (
          <div className="space-y-2">
            <div className="flex items-center gap-2"><Spinner />{state.message}</div>
            {state.progress != null && <Progress value={state.progress} />}
          </div>
        )}
        {state.error && <p role="alert" className="text-destructive">{state.error}</p>}
        {state.result && (
          <>
            <p>{state.result.preview_summary}</p>
            <p className="text-sm text-muted-foreground">{state.result.notice}</p>
            <SnapshotSkipNotice paths={state.result.skipped_paths} count={state.result.skipped_count} />
            {actions.isPending && <Spinner />}
            {actions.isError && (
              <p role="alert">
                暂时无法读取预览明细，请重试。
                <Button variant="outline" onClick={() => void actions.refetch()}>重试</Button>
              </p>
            )}
            <div className="max-h-96 overflow-y-auto space-y-2">
              {actions.data?.actions.map((action, index) => (
                <div key={`${cursor}-${index}`} className="rounded border p-2 text-sm">
                  <span className="mr-2">{labels[action.action]}</span>
                  <span className="font-mono break-all">{action.item}</span>
                </div>
              ))}
            </div>
            {actions.data && (
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  disabled={cursors.length === 1}
                  onClick={() => setCursors(previous => previous.slice(0, -1))}
                >上一页</Button>
                <Button
                  variant="outline"
                  disabled={nextCursor == null}
                  onClick={() => { if (nextCursor != null) setCursors(previous => [...previous, nextCursor]) }}
                >下一页</Button>
              </div>
            )}
          </>
        )}
        <DialogFooter>
          {state.active && (
            <Button
              variant="destructive"
              disabled={!state.taskId || state.cancelling}
              onClick={() => void state.cancel()}
            >停止准备</Button>
          )}
          {state.result && onRestore && (
            <Button onClick={() => onRestore(state.result!.preview_id)}>按此预览恢复</Button>
          )}
          <Button variant="outline" onClick={onClose}>关闭</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
