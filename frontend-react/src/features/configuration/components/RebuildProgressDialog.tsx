import React, { useEffect, useRef } from 'react'
import { toast } from 'sonner'
import { Progress } from '@/shared/ui/progress'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/shared/ui/dialog'
import { useTaskQueries } from '@/features/tasks/queries'

interface RebuildProgressDialogProps {
  open: boolean
  taskId: string | null
  onFailure?: (code?: string) => void
  onClose: () => void
  onComplete: (result?: Record<string, unknown>) => void
}

const RebuildProgressDialog: React.FC<RebuildProgressDialogProps> = ({
  open,
  taskId,
  onFailure,
  onClose,
  onComplete,
}) => {
  const handledTask = useRef<string | null>(null)

  const { useTask } = useTaskQueries()
  const { data: task } = useTask(taskId || '')

  useEffect(() => {
    if (!open || !task || task.taskId !== taskId || handledTask.current === taskId) return
    if (task.status !== 'completed' && task.status !== 'failed' && task.status !== 'cancelled') return
    handledTask.current = taskId

    if (task.status === 'completed') {
      toast.success('服务器配置更新完成')
      onComplete(task.result)
    } else {
      toast.error(task.status === 'cancelled' ? '配置更新已取消' : `配置更新失败: ${task.error || task.message || '请查看任务详情'}`)
      onFailure?.(task.errorCode)
      onClose()
    }
  }, [open, taskId, task, onComplete, onClose, onFailure])

  const isActive = task?.status === 'running' || task?.status === 'pending'

  return (
    <Dialog open={open} onOpenChange={(o) => !o && !isActive && onClose()}>
      <DialogContent showCloseButton={!isActive}>
        <DialogHeader>
          <DialogTitle>正在更新服务器配置</DialogTitle>
        </DialogHeader>
        <div className="py-4">
          <Progress value={task?.progress ?? 0} />
          <div className="text-muted-foreground text-sm mt-2 text-center">
            {task?.message || '准备中...'}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}

export default RebuildProgressDialog
