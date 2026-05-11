import React, { useEffect, useMemo, useState } from 'react'
import { toast } from 'sonner'
import { AlertTriangle, ArrowRightLeft, FolderInput, Trash2 } from 'lucide-react'

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Separator } from '@/components/ui/separator'
import { Spinner } from '@/components/ui/spinner'
import { useServerMutations } from '@/hooks/mutations/useServerMutations'
import type { SyncDryRunEntry, SyncEntryError } from '@/types/lifecycle'

interface SyncWithFilesystemDialogProps {
  open: boolean
  onClose: () => void
}

const SyncWithFilesystemDialog: React.FC<SyncWithFilesystemDialogProps> = ({
  open,
  onClose,
}) => {
  const { useSyncServers } = useServerMutations()
  const syncMutation = useSyncServers()

  const [preview, setPreview] = useState<SyncDryRunEntry[]>([])
  const [errors, setErrors] = useState<SyncEntryError[]>([])
  const [previewError, setPreviewError] = useState<string | null>(null)
  const [needsForce, setNeedsForce] = useState(false)
  const [hasLoaded, setHasLoaded] = useState(false)

  const adoptEntries = useMemo(
    () => preview.filter((p) => p.action === 'adopt'),
    [preview],
  )
  const deactivateEntries = useMemo(
    () => preview.filter((p) => p.action === 'deactivate'),
    [preview],
  )

  const fetchPreview = async () => {
    setPreviewError(null)
    setNeedsForce(false)
    try {
      const result = await syncMutation.mutateAsync({ dry_run: true })
      setPreview(result.preview)
      setErrors(result.errors)
      setHasLoaded(true)
    } catch (e: any) {
      if (e?.status === 409 && typeof e?.message === 'string' && e.message.includes('force=true')) {
        setNeedsForce(true)
        setPreview([])
        setErrors([])
        setHasLoaded(true)
        return
      }
      setPreviewError(e?.message || '获取预览失败')
    }
  }

  useEffect(() => {
    if (open) {
      setPreview([])
      setErrors([])
      setPreviewError(null)
      setNeedsForce(false)
      setHasLoaded(false)
      fetchPreview()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  const handleApply = async (force = false) => {
    try {
      const result = await syncMutation.mutateAsync({ dry_run: false, force })
      const adopted = result.adopted.length
      const removed = result.removed.length
      const errored = result.errors.length
      toast.success(
        `同步完成：导入 ${adopted}，停用 ${removed}` +
          (errored > 0 ? `，${errored} 个失败` : ''),
      )
      onClose()
    } catch (e: any) {
      if (e?.status === 409 && typeof e?.message === 'string' && e.message.includes('force=true')) {
        setNeedsForce(true)
        return
      }
      toast.error(`同步失败：${e?.message || '未知错误'}`)
    }
  }

  const renderAdoptEntries = () => (
    <div className="space-y-2">
      <div className="flex items-center gap-2 text-sm font-semibold">
        <FolderInput className="h-4 w-4" />
        <span>将导入 ({adoptEntries.length})</span>
      </div>
      {adoptEntries.length === 0 ? (
        <p className="text-sm text-muted-foreground pl-6">无</p>
      ) : (
        <div className="space-y-1 pl-6">
          {adoptEntries.map((e) => (
            <div
              key={`adopt-${e.server_id}`}
              className="flex items-center justify-between text-sm border-l-2 border-green-500 pl-3 py-1"
            >
              <span className="font-mono">{e.server_id}</span>
              <span className="text-muted-foreground text-xs">
                端口 {e.game_port} / RCON {e.rcon_port}
              </span>
            </div>
          ))}
          <Alert>
            <AlertTitle className="text-sm">导入说明</AlertTitle>
            <AlertDescription>
              将作为直连模式导入；模板绑定不会被恢复。
            </AlertDescription>
          </Alert>
        </div>
      )}
    </div>
  )

  const renderDeactivateEntries = () => (
    <div className="space-y-2">
      <div className="flex items-center gap-2 text-sm font-semibold text-destructive">
        <Trash2 className="h-4 w-4" />
        <span>将停用 ({deactivateEntries.length})</span>
      </div>
      {deactivateEntries.length === 0 ? (
        <p className="text-sm text-muted-foreground pl-6">无</p>
      ) : (
        <div className="space-y-1 pl-6">
          {deactivateEntries.map((e) => {
            const cronCount = e.restart_cronjob_count ?? 0
            const sessionCount = e.open_session_count ?? 0
            return (
              <div
                key={`deactivate-${e.server_id}`}
                className="flex items-center justify-between text-sm border-l-2 border-destructive pl-3 py-1"
              >
                <span className="font-mono">{e.server_id}</span>
                <div className="flex items-center gap-2">
                  {cronCount > 0 && (
                    <Badge variant="destructive">{cronCount} 个重启计划</Badge>
                  )}
                  {sessionCount > 0 && (
                    <Badge variant="destructive">{sessionCount} 个在线会话</Badge>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )

  const renderErrors = () => {
    if (errors.length === 0) return null
    return (
      <div className="space-y-2">
        <div className="flex items-center gap-2 text-sm font-semibold text-destructive">
          <AlertTriangle className="h-4 w-4" />
          <span>验证失败 ({errors.length})</span>
        </div>
        <div className="space-y-1 pl-6">
          {errors.map((e, idx) => (
            <div
              key={`error-${e.server_id}-${idx}`}
              className="text-sm border-l-2 border-yellow-500 pl-3 py-1"
            >
              <div className="font-mono">{e.server_id}</div>
              <div className="text-xs text-muted-foreground">{e.error}</div>
            </div>
          ))}
        </div>
      </div>
    )
  }

  const nothingToDo =
    hasLoaded &&
    !needsForce &&
    adoptEntries.length === 0 &&
    deactivateEntries.length === 0 &&
    errors.length === 0

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <ArrowRightLeft className="h-5 w-5" />
            与文件系统同步
          </DialogTitle>
          <DialogDescription>
            对比服务器目录与数据库记录，将磁盘上的新服务器导入数据库，
            并停用磁盘上已不存在的旧记录。
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {syncMutation.isPending && !hasLoaded ? (
            <div className="flex justify-center py-8">
              <Spinner className="size-6" />
            </div>
          ) : previewError ? (
            <Alert variant="destructive">
              <AlertTitle>无法获取预览</AlertTitle>
              <AlertDescription>{previewError}</AlertDescription>
            </Alert>
          ) : needsForce ? (
            <Alert variant="destructive">
              <AlertTitle className="flex items-center gap-2">
                <AlertTriangle className="h-4 w-4" />
                服务器目录读取为空
              </AlertTitle>
              <AlertDescription className="space-y-2">
                <p>
                  当前文件系统中没有任何服务器目录，但数据库中还存在活动记录。
                  这可能意味着挂载点或权限出了问题。如果确认要停用所有数据库记录，
                  请点击下方“强制应用”。
                </p>
              </AlertDescription>
            </Alert>
          ) : nothingToDo ? (
            <Alert>
              <AlertTitle>无需同步</AlertTitle>
              <AlertDescription>
                文件系统与数据库记录已保持一致。
              </AlertDescription>
            </Alert>
          ) : (
            <ScrollArea className="max-h-[50vh]">
              <div className="space-y-4 pr-2">
                {renderAdoptEntries()}
                <Separator />
                {renderDeactivateEntries()}
                {errors.length > 0 && (
                  <>
                    <Separator />
                    {renderErrors()}
                  </>
                )}
              </div>
            </ScrollArea>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            取消
          </Button>
          {needsForce ? (
            <Button
              variant="destructive"
              onClick={() => handleApply(true)}
              disabled={syncMutation.isPending}
            >
              {syncMutation.isPending ? <Spinner className="mr-2 size-4" /> : null}
              强制应用
            </Button>
          ) : (
            <Button
              onClick={() => handleApply(false)}
              disabled={syncMutation.isPending || nothingToDo || !!previewError}
            >
              {syncMutation.isPending ? <Spinner className="mr-2 size-4" /> : null}
              应用同步
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export default SyncWithFilesystemDialog
