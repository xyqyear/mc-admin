import React, { useEffect } from 'react'
import { Modal, Progress, App } from 'antd'
import { useQueryClient } from '@tanstack/react-query'
import { useTaskQueries } from '@/hooks/queries/base/useTaskQueries'
import { queryKeys } from '@/utils/api'

interface RebuildProgressModalProps {
  open: boolean
  taskId: string | null
  serverId: string
  onClose: () => void
  onComplete: () => void
}

const RebuildProgressModal: React.FC<RebuildProgressModalProps> = ({
  open,
  taskId,
  serverId,
  onClose,
  onComplete,
}) => {
  const { message } = App.useApp()
  const queryClient = useQueryClient()

  const { useTask } = useTaskQueries()
  const { data: task } = useTask(taskId || '')

  useEffect(() => {
    if (!task) return

    if (task.status === 'completed') {
      message.success('服务器配置更新完成')
      // Invalidate server-related queries after rebuild completion
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
      message.error(`配置更新失败: ${task.error}`)
      onClose()
    }
  }, [task, serverId, message, queryClient, onComplete, onClose])

  const getProgressStatus = () => {
    if (!task) return 'normal'
    if (task.status === 'running') return 'active'
    if (task.status === 'failed') return 'exception'
    if (task.status === 'completed') return 'success'
    return 'normal'
  }

  const isActive = task?.status === 'running' || task?.status === 'pending'

  return (
    <Modal
      open={open}
      title="正在更新服务器配置"
      footer={null}
      closable={!isActive}
      onCancel={isActive ? undefined : onClose}
      maskClosable={false}
    >
      <div className="py-4">
        <Progress
          percent={task?.progress ?? 0}
          status={getProgressStatus()}
        />
        <div className="text-gray-500 text-sm mt-2 text-center">
          {task?.message || '准备中...'}
        </div>
      </div>
    </Modal>
  )
}

export default RebuildProgressModal
