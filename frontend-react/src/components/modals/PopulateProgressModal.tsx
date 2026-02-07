import React, { useEffect } from 'react'
import { Modal, Progress, App } from 'antd'
import { useQueryClient } from '@tanstack/react-query'
import { useTaskQueries } from '@/hooks/queries/base/useTaskQueries'
import { queryKeys } from '@/utils/api'

interface PopulateProgressModalProps {
  open: boolean
  taskId: string | null
  onClose: () => void
  onComplete: () => void
  serverId: string
}

const PopulateProgressModal: React.FC<PopulateProgressModalProps> = ({
  open,
  taskId,
  onClose,
  onComplete,
  serverId,
}) => {
  const { message } = App.useApp()
  const queryClient = useQueryClient()

  const { useTask } = useTaskQueries()
  const { data: task } = useTask(taskId || '')

  useEffect(() => {
    if (!task) return

    if (task.status === 'completed') {
      message.success('服务器文件替换完成!')
      // Invalidate related caches
      queryClient.invalidateQueries({
        queryKey: queryKeys.serverInfos.detail(serverId),
      })
      queryClient.invalidateQueries({
        queryKey: [...queryKeys.serverRuntimes.detail(serverId), 'disk'],
      })
      queryClient.invalidateQueries({
        queryKey: queryKeys.files.lists(serverId),
      })
      queryClient.invalidateQueries({ queryKey: queryKeys.servers() })
      onComplete()
    } else if (task.status === 'failed') {
      message.error(`填充失败: ${task.error}`)
      onClose()
    }
  }, [task, task?.status, task?.error, serverId, message, queryClient, onComplete, onClose])

  const getProgressStatus = () => {
    if (!task) return 'normal'
    if (task.status === 'running') return 'active'
    if (task.status === 'failed') return 'exception'
    if (task.status === 'completed') return 'success'
    return 'normal'
  }

  return (
    <Modal
      open={open}
      title="正在填充服务器文件"
      footer={null}
      closable={task?.status !== 'running' && task?.status !== 'pending'}
      maskClosable={false}
      onCancel={onClose}
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

export default PopulateProgressModal
