import React, { useEffect } from 'react'
import { toast } from 'sonner'
import { useQueryClient } from '@tanstack/react-query'
import { Progress } from '@/components/ui/progress'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { useTaskQueries } from '@/hooks/queries/base/useTaskQueries'
import { queryKeys } from '@/utils/api'

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
  serverId,
}) => {
  const queryClient = useQueryClient()

  const { useTask } = useTaskQueries()
  const { data: task } = useTask(taskId || '')

  useEffect(() => {
    if (!task) return

    if (task.status === 'completed') {
      toast.success('服务器文件替换完成!')
      queryClient.invalidateQueries({
        queryKey: queryKeys.serverInfos.detail(serverId),
      })
      queryClient.invalidateQueries({
        queryKey: queryKeys.serverRuntimes.disk(serverId),
      })
      queryClient.invalidateQueries({
        queryKey: queryKeys.files.lists(serverId),
      })
      queryClient.invalidateQueries({ queryKey: queryKeys.servers() })
      onComplete()
    } else if (task.status === 'failed') {
      toast.error(`填充失败: ${task.error}`)
      onClose()
    }
  }, [task, task?.status, task?.error, serverId, queryClient, onComplete, onClose])

  const isActive = task?.status === 'running' || task?.status === 'pending'

  return (
    <Dialog open={open} onOpenChange={(o) => !o && !isActive && onClose()}>
      <DialogContent showCloseButton={!isActive}>
        <DialogHeader>
          <DialogTitle>正在填充服务器文件</DialogTitle>
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

export default PopulateProgressDialog
