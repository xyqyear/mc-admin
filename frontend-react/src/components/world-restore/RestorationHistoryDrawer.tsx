import React, { useMemo, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Loader2, RotateCcw, Undo2 } from 'lucide-react'

import { Button } from '@/components/ui/button'
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet'
import { Spinner } from '@/components/ui/spinner'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { useConfirm } from '@/hooks/useConfirm'
import { useEventStream } from '@/hooks/useEventStream'
import { useRestorations } from '@/hooks/queries/base/useWorldRestoreQueries'
import { queryKeys } from '@/utils/api'
import type {
  RestorationResponse,
  RestoreEvent,
} from '@/types/WorldRestore'

import { RestoreProgressCard } from './RestoreProgressCard'
import {
  applyRestoreEvent,
  initialProgress,
  type RestoreProgressState,
} from './restoreProgress'

interface RestorationHistoryDrawerProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  serverId: string
  serverStopped: boolean
}

const TYPE_LABEL: Record<RestorationResponse['type'], string> = {
  world: '整个世界',
  dimension: '整个维度',
  regions: '区域',
  chunks: '区块',
}

const STATUS_TONE: Record<
  RestorationResponse['status'],
  { label: string; className: string }
> = {
  running: {
    label: '运行中',
    className: 'bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-200',
  },
  succeeded: {
    label: '成功',
    className:
      'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-200',
  },
  failed: {
    label: '失败',
    className: 'bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-200',
  },
  interrupted: {
    label: '已中断',
    className:
      'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-200',
  },
}

function formatTime(iso: string | null): string {
  if (!iso) return '-'
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString()
}

export const RestorationHistoryDrawer: React.FC<
  RestorationHistoryDrawerProps
> = ({ open, onOpenChange, serverId, serverStopped }) => {
  const { confirm, confirmDialog } = useConfirm()
  const queryClient = useQueryClient()
  const restorationsQ = useRestorations(open ? serverId : undefined)

  const [rollbackId, setRollbackId] = useState<string | null>(null)
  const [rollbackState, setRollbackState] =
    useState<RestoreProgressState>(initialProgress)

  useEventStream<RestoreEvent>({
    enabled: !!rollbackId && !rollbackState.error && !rollbackState.done,
    url: rollbackId
      ? `/servers/${serverId}/world-restore/restorations/${rollbackId}/rollback`
      : '',
    method: 'POST',
    onEvent: (ev) => setRollbackState((prev) => applyRestoreEvent(prev, ev)),
    onClose: () =>
      setRollbackState((prev) =>
        prev.done || prev.error
          ? prev
          : { ...prev, active: false, error: '连接中断' },
      ),
    onError: (msg) =>
      setRollbackState((prev) => ({ ...prev, active: false, error: msg })),
  })

  React.useEffect(() => {
    if (rollbackState.done) {
      toast.success('回滚完成')
      queryClient.invalidateQueries({ queryKey: queryKeys.worldRestore.all })
    } else if (rollbackState.error) {
      toast.error('回滚失败', { description: rollbackState.error })
    }
  }, [rollbackState.done, rollbackState.error, queryClient])

  const startRollback = (row: RestorationResponse) => {
    if (!row.safety_snapshot_id) {
      toast.error('该恢复没有安全快照，无法回滚')
      return
    }
    if (!serverStopped) {
      toast.error('服务器运行中，无法回滚。请先停止服务器。')
      return
    }
    confirm({
      title: '回滚确认',
      description: `将从安全快照 ${row.safety_snapshot_id.slice(0, 8)} 回滚此次恢复。是否继续？`,
      confirmText: '开始回滚',
      variant: 'destructive',
      onConfirm: () => {
        setRollbackState({
          active: true,
          percent: 0,
          message: '准备开始',
          log: [],
          done: false,
          error: null,
        })
        setRollbackId(row.id)
      },
    })
  }

  const finishRollback = () => {
    setRollbackId(null)
    setRollbackState(initialProgress)
    queryClient.invalidateQueries({ queryKey: queryKeys.worldRestore.all })
  }

  const rows = useMemo(
    () => restorationsQ.data?.restorations ?? [],
    [restorationsQ.data],
  )

  return (
    <Sheet
      open={open}
      onOpenChange={(o) => {
        if (!o && rollbackState.active) return
        if (!o) finishRollback()
        onOpenChange(o)
      }}
    >
      <SheetContent
        side="right"
        className="w-full sm:max-w-2xl flex flex-col overflow-hidden"
      >
        <SheetHeader>
          <SheetTitle>恢复历史</SheetTitle>
          <SheetDescription>
            最近的恢复记录（自动每 5 秒刷新）
          </SheetDescription>
        </SheetHeader>

        <div className="flex-1 overflow-auto px-4 pb-4 space-y-3">
          {rollbackId && (
            <>
              <RestoreProgressCard state={rollbackState} title="正在回滚" />
              {(rollbackState.done || rollbackState.error) && (
                <div className="flex justify-end">
                  <Button variant="outline" onClick={finishRollback}>
                    返回历史
                  </Button>
                </div>
              )}
            </>
          )}

          {!rollbackId && (
            <>
              {restorationsQ.isLoading && (
                <div className="flex items-center justify-center py-8">
                  <Spinner />
                </div>
              )}
              {restorationsQ.isError && (
                <Alert variant="destructive">
                  <AlertTitle>加载失败</AlertTitle>
                  <AlertDescription>无法获取恢复历史</AlertDescription>
                </Alert>
              )}
              {!restorationsQ.isLoading && rows.length === 0 && (
                <Alert>
                  <AlertTitle>暂无恢复记录</AlertTitle>
                  <AlertDescription>
                    完成一次恢复操作后会在此处显示，并支持一键回滚。
                  </AlertDescription>
                </Alert>
              )}
              {rows.map((row) => {
                const tone = STATUS_TONE[row.status]
                // The backend reports per-row snapshot existence by checking
                // the restic repo at request time. If the safety snapshot has
                // been deleted, rollback is impossible — hide the button.
                const canRollback =
                  (row.status === 'succeeded' || row.status === 'interrupted') &&
                  !!row.safety_snapshot_id &&
                  row.safety_snapshot_exists &&
                  !row.is_rollback
                return (
                  <div
                    key={row.id}
                    className="rounded-md border p-3 space-y-2"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex items-center gap-2">
                        <Badge className={tone.className}>{tone.label}</Badge>
                        <span className="text-sm">
                          {row.is_rollback ? (
                            <span className="inline-flex items-center gap-1">
                              <Undo2 className="h-3.5 w-3.5" />
                              回滚 · {TYPE_LABEL[row.type]}
                            </span>
                          ) : (
                            <span className="inline-flex items-center gap-1">
                              <RotateCcw className="h-3.5 w-3.5" />
                              恢复 · {TYPE_LABEL[row.type]}
                            </span>
                          )}
                        </span>
                      </div>
                      <div className="flex items-center gap-2">
                        {canRollback && (
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => startRollback(row)}
                          >
                            <Undo2 className="mr-1 h-3.5 w-3.5" />
                            回滚
                          </Button>
                        )}
                        {row.status === 'running' && (
                          <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
                        )}
                      </div>
                    </div>
                    <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs text-muted-foreground">
                      <div>
                        开始：
                        <span className="text-foreground">
                          {formatTime(row.started_at)}
                        </span>
                      </div>
                      <div>
                        结束：
                        <span className="text-foreground">
                          {formatTime(row.finished_at)}
                        </span>
                      </div>
                      <div>
                        源快照：
                        <span className="font-mono text-foreground">
                          {row.source_snapshot_id.slice(0, 8)}
                        </span>
                        {!row.source_snapshot_exists && (
                          <span className="ml-1 text-destructive">(已删除)</span>
                        )}
                      </div>
                      <div>
                        安全快照：
                        <span className="font-mono text-foreground">
                          {row.safety_snapshot_id
                            ? row.safety_snapshot_id.slice(0, 8)
                            : '—'}
                        </span>
                        {row.safety_snapshot_id &&
                          !row.safety_snapshot_exists && (
                            <span className="ml-1 text-destructive">
                              (已删除)
                            </span>
                          )}
                      </div>
                    </div>
                    {row.status === 'interrupted' &&
                      !!row.safety_snapshot_id &&
                      row.safety_snapshot_exists && (
                        <Alert>
                          <AlertTitle className="text-sm">需要回滚</AlertTitle>
                          <AlertDescription className="text-xs">
                            此次恢复在执行过程中被中断，建议立即从安全快照回滚以避免世界处于不一致状态。
                          </AlertDescription>
                        </Alert>
                      )}
                    {row.error_message && (
                      <div className="text-xs text-destructive break-all">
                        错误：{row.error_message}
                      </div>
                    )}
                  </div>
                )
              })}
            </>
          )}
        </div>
      </SheetContent>
      {confirmDialog}
    </Sheet>
  )
}

export default RestorationHistoryDrawer
