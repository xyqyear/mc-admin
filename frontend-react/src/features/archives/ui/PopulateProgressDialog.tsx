import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/shared/ui/dialog'
import { Progress } from '@/shared/ui/progress'
import { useTask } from '@/features/tasks/queries';
import { TaskResultFeedback } from '@/features/tasks/ui/TaskResultFeedback'
import React, { useEffect, useRef } from 'react'
import { toast } from 'sonner'

interface PopulateProgressDialogProps {
  open: boolean
  taskId: string | null
  onClose: () => void
  onComplete: () => void
  serverId: string
}

const PopulateProgressDialog: React.FC<PopulateProgressDialogProps> = ({
  open,
  taskId,
  onClose,
  onComplete,
}) => {
  const handled = useRef<string | null>(null)
  const { data: task, resultReady } = useTask(taskId || '')

  useEffect(() => {
    if (!open || !task || !resultReady || handled.current === task.taskId || task.status === 'running' || task.status === 'pending') return
    handled.current = task.taskId

    if (task.status === 'completed') {
      toast.success('服务器文件替换完成!')
      onComplete()
    } else if (task.status === 'failed') {
      toast.error(`填充失败: ${task.error}`)
      onClose()
    } else if (task.status === 'cancelled') {
      toast.info('文件替换已取消')
      onClose()
    }
  }, [open, task, task?.status, task?.error, resultReady, onComplete, onClose])


  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent showCloseButton>
        <DialogHeader>
          <DialogTitle>正在填充服务器文件</DialogTitle>
        </DialogHeader>
        <div className="py-4">
          <TaskResultFeedback taskId={taskId ?? ''} />
          <Progress value={task?.progress ?? 0} />
          <div className="text-muted-foreground text-sm mt-2 text-center">
            {task?.message || '准备中...'}
            <p>关闭窗口后任务仍会继续，可在任务中心查看进度。</p>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}

export default PopulateProgressDialog
