import { Eye, RotateCcw } from 'lucide-react'
import React, { useState } from 'react'
import { toast } from 'sonner'
import { useRestorationStream } from '@/features/world/restore/useRestorationStream'

import { Alert, AlertDescription, AlertTitle } from '@/shared/ui/alert'
import { Button } from '@/shared/ui/button'
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/shared/ui/sheet'
import { Spinner } from '@/shared/ui/spinner'
import type { RestorationSelection } from '@/features/world/restore/contracts'
import { useEligibleSnapshots } from '@/features/world/restore/queries'
import { useConfirm } from '@/shared/hooks/useConfirm'

import {
  RestorePreviewModal,
  type RestorePreviewRequest,
} from '@/features/world/restore/components/RestorePreviewModal'
import { RestoreProgressCard } from '@/shared/operations/components/RestoreProgressCard'

interface SnapshotPickerProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  serverId: string
  selection: RestorationSelection | null
}

const SCOPE_LABEL: Record<string, string> = {
  world: '整个世界',
  dimension: '整个维度',
  regions: '所选区域',
  chunks: '所选区块',
}

function formatTime(iso: string): string {
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString()
}

export const SnapshotPicker: React.FC<SnapshotPickerProps> = ({
  open,
  onOpenChange,
  serverId,
  selection,
}) => {
  const { confirm, confirmDialog } = useConfirm()
  const eligibleQ = useEligibleSnapshots(serverId, open ? selection : null)

  const { command, state: restoreState, start, reset } = useRestorationStream(serverId)
  const restoreFor = command?.kind === 'restore' ? command.request.source_snapshot_id : null

  // Captures the selection at click time so the modal's SSE body is stable
  // even if the page selection changes underneath.
  const [previewReq, setPreviewReq] =
    useState<RestorePreviewRequest | null>(null)

  const handleRowRestore = (snapshotId: string, shortId: string) => {
    if (!selection) return
    confirm({
      title: '恢复确认',
      description: `将先创建一个安全快照，然后从 ${shortId} 恢复 ${SCOPE_LABEL[selection.type] ?? selection.type}。是否继续？`,
      confirmText: '开始恢复',
      variant: 'destructive',
      onConfirm: () => {
        start({ kind: 'restore', request: { source_snapshot_id: snapshotId, selection } })
      },
    })
  }

  const closeAfterCleanup = () => {
    reset()
    onOpenChange(false)
  }

  React.useEffect(() => {
    if (restoreState.done) {
      toast.success('恢复完成')
    } else if (restoreState.error) {
      toast.error('恢复失败', { description: restoreState.error })
    }
  }, [restoreState.done, restoreState.error])

  const headerSubtitle = selection ? (SCOPE_LABEL[selection.type] ?? selection.type) : ''

  return (
    <Sheet
      open={open}
      onOpenChange={(o) => {
        if (!o && restoreState.active) return
        if (!o) {
          reset()
        }
        onOpenChange(o)
      }}
    >
      <SheetContent
        side="right"
        className="w-full sm:max-w-lg flex flex-col overflow-hidden"
      >
        <SheetHeader>
          <SheetTitle>选择快照恢复</SheetTitle>
          <SheetDescription>{headerSubtitle}</SheetDescription>
        </SheetHeader>

        <div className="flex-1 overflow-auto px-4 pb-4 space-y-3">
          {restoreFor ? (
            <>
              <RestoreProgressCard state={restoreState} />
              {(restoreState.done || restoreState.error) && (
                <div className="flex justify-end">
                  <Button onClick={closeAfterCleanup}>关闭</Button>
                </div>
              )}
            </>
          ) : (
            <>
              {eligibleQ.isLoading && (
                <div className="flex items-center justify-center py-8">
                  <Spinner />
                </div>
              )}
              {eligibleQ.isError && (
                <Alert variant="destructive">
                  <AlertTitle>加载快照失败</AlertTitle>
                  <AlertDescription>
                    无法获取适用于当前选择的快照列表
                  </AlertDescription>
                </Alert>
              )}
              {!eligibleQ.isLoading &&
                !eligibleQ.isError &&
                (eligibleQ.data?.snapshots.length ?? 0) === 0 && (
                  <Alert>
                    <AlertTitle>没有可用快照</AlertTitle>
                    <AlertDescription>
                      该范围内还没有覆盖完整路径的快照。请先创建快照后再尝试恢复。
                    </AlertDescription>
                  </Alert>
                )}
              {(eligibleQ.data?.snapshots ?? []).map((s) => (
                <div
                  key={s.id}
                  className="rounded-md border p-3 space-y-2 hover:bg-muted/40"
                >
                  <div className="flex items-center justify-between">
                    <div className="space-y-0.5">
                      <div className="font-mono text-sm font-medium">
                        {s.short_id}
                      </div>
                      <div className="text-xs text-muted-foreground">
                        {formatTime(s.time)}
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      {selection &&
                        selection.type !== 'world' &&
                        selection.type !== 'dimension' && (
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() =>
                              setPreviewReq({
                                sourceSnapshotId: s.id,
                                selection,
                              })
                            }
                          >
                            <Eye className="mr-1 h-3.5 w-3.5" />
                            预览
                          </Button>
                        )}
                      <Button
                        size="sm"
                        onClick={() => handleRowRestore(s.id, s.short_id)}
                      >
                        <RotateCcw className="mr-1 h-3.5 w-3.5" />
                        恢复
                      </Button>
                    </div>
                  </div>
                  {s.paths.length > 0 && (
                    <div className="text-xs text-muted-foreground break-all space-y-0.5">
                      <div>路径：</div>
                      {s.paths.slice(0, 5).map((p) => (
                        <div key={p} className="pl-3">
                          {p}
                        </div>
                      ))}
                      {s.paths.length > 5 && (
                        <div className="pl-3">
                          ……还有 {s.paths.length - 5} 条
                        </div>
                      )}
                    </div>
                  )}
                </div>
              ))}
            </>
          )}
        </div>
      </SheetContent>
      {confirmDialog}
      <RestorePreviewModal
        serverId={serverId}
        request={previewReq}
        onClose={() => setPreviewReq(null)}
      />
    </Sheet>
  )
}

export default SnapshotPicker
