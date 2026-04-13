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

interface RebuildProgressDialogProps {
  open: boolean
  taskId: string | null
  serverId: string
  onClose: () => void
  onComplete: () => void
}

const RebuildProgressDialog: React.FC<RebuildProgressDialogProps> = ({
  open,
  taskId,
  serverId,
  onClose,
  onComplete,
}) => {
  const queryClient = useQueryClient()

  const { useTask } = useTaskQueries()
  const { data: task } = useTask(taskId || '')

  useEffect(() => {
    if (!task) return

    if (task.status === 'completed') {
      toast.success('服务器配置更新完成')
      queryClient.invalidateQueries({
        queryKey: queryKeys.serverInfos.detail(serverId),
      })
      queryClient.invalidateQueries({
        queryKey: queryKeys.compose.detail(serverId),
      })
      queryClient.invalidateQueries({
        queryKey: queryKeys.serverStatuses.detail(serverId),
      })
      queryClient.invalidateQueries({
        queryKey: queryKeys.serverRuntimes.detail(serverId),
      })
      queryClient.invalidateQueries({
        queryKey: queryKeys.servers(),
      })
      queryClient.invalidateQueries({
        queryKey: queryKeys.players.serverOnline(serverId),
      })
      onComplete()
    } else if (task.status === 'failed') {
      toast.error(`配置更新失败: ${task.error}`)
      onClose()
    }
  }, [task, serverId, queryClient, onComplete, onClose])

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
