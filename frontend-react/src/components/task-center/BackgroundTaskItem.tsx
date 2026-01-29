import React from 'react'
import { Progress, Button, Typography, Tooltip, Popover } from 'antd'
import {
  FileZipOutlined,
  CameraOutlined,
  PlayCircleOutlined,
  StopOutlined,
  ReloadOutlined,
  CloseOutlined,
  CheckCircleOutlined,
  ExclamationCircleOutlined,
  LoadingOutlined,
  ClockCircleOutlined,
} from '@ant-design/icons'
import type { BackgroundTask, BackgroundTaskType } from '@/stores/useBackgroundTaskStore'

const { Text } = Typography

interface BackgroundTaskItemProps {
  task: BackgroundTask
  onCancel: (taskId: string) => void
  onRemove: (taskId: string) => void
}

const getTaskTypeIcon = (taskType: BackgroundTaskType) => {
  switch (taskType) {
    case 'archive_create':
    case 'archive_extract':
      return <FileZipOutlined />
    case 'snapshot_create':
    case 'snapshot_restore':
      return <CameraOutlined />
    case 'server_start':
      return <PlayCircleOutlined />
    case 'server_stop':
      return <StopOutlined />
    case 'server_restart':
      return <ReloadOutlined />
    default:
      return <LoadingOutlined />
  }
}

const getTaskTypeName = (taskType: BackgroundTaskType): string => {
  switch (taskType) {
    case 'archive_create':
      return '创建压缩包'
    case 'archive_extract':
      return '解压文件'
    case 'snapshot_create':
      return '创建快照'
    case 'snapshot_restore':
      return '恢复快照'
    case 'server_start':
      return '启动服务器'
    case 'server_stop':
      return '停止服务器'
    case 'server_restart':
      return '重启服务器'
    default:
      return '未知任务'
  }
}

const getStatusIcon = (status: BackgroundTask['status']) => {
  switch (status) {
    case 'pending':
      return <ClockCircleOutlined className="text-gray-500" />
    case 'running':
      return <LoadingOutlined className="text-blue-500" spin />
    case 'completed':
      return <CheckCircleOutlined className="text-green-500" />
    case 'failed':
      return <ExclamationCircleOutlined className="text-red-500" />
    case 'cancelled':
      return <StopOutlined className="text-gray-500" />
    default:
      return <LoadingOutlined />
  }
}

const getStatusText = (status: BackgroundTask['status']): string => {
  switch (status) {
    case 'pending':
      return '等待中'
    case 'running':
      return '进行中'
    case 'completed':
      return '已完成'
    case 'failed':
      return '失败'
    case 'cancelled':
      return '已取消'
    default:
      return '未知'
  }
}

const getElapsedTime = (task: BackgroundTask): string => {
  const startTime = task.startedAt || task.createdAt
  const endTime = task.endedAt || Date.now()
  const elapsed = endTime - startTime
  const seconds = Math.floor(elapsed / 1000)
  if (seconds < 60) return `${seconds}秒`
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes}分${seconds % 60}秒`
  const hours = Math.floor(minutes / 60)
  return `${hours}时${minutes % 60}分`
}

const BackgroundTaskItem: React.FC<BackgroundTaskItemProps> = ({
  task,
  onCancel,
  onRemove,
}) => {
  const isActive = task.status === 'pending' || task.status === 'running'
  const canCancel = isActive && task.cancellable

  const taskInfo = (
    <div className="space-y-2 min-w-48">
      <div>
        <Text strong>任务类型：</Text>
        <Text>{getTaskTypeName(task.taskType)}</Text>
      </div>
      {task.name && (
        <div>
          <Text strong>名称：</Text>
          <Text>{task.name}</Text>
        </div>
      )}
      {task.serverId && (
        <div>
          <Text strong>服务器：</Text>
          <Text>{task.serverId}</Text>
        </div>
      )}
      <div>
        <Text strong>状态：</Text>
        <Text>{getStatusText(task.status)}</Text>
      </div>
      <div>
        <Text strong>用时：</Text>
        <Text>{getElapsedTime(task)}</Text>
      </div>
      {task.message && (
        <div>
          <Text strong>进度：</Text>
          <Text className="break-all">{task.message}</Text>
        </div>
      )}
      {task.error && (
        <div>
          <Text strong>错误：</Text>
          <Text type="danger" className="break-all">{task.error}</Text>
        </div>
      )}
    </div>
  )

  const handleAction = () => {
    if (canCancel) {
      onCancel(task.taskId)
    } else if (!isActive) {
      onRemove(task.taskId)
    }
  }

  return (
    <div className="flex items-center gap-2 p-2 hover:bg-gray-50 rounded transition-colors">
      <span className="flex-shrink-0 w-5 text-center">
        {getStatusIcon(task.status)}
      </span>

      <div className="flex-1 min-w-0">
        <Popover content={taskInfo} title="任务详情" placement="left">
          <div className="cursor-pointer">
            <div className="flex items-center gap-1.5">
              <span className="flex-shrink-0 text-gray-500">
                {getTaskTypeIcon(task.taskType)}
              </span>
              <Text
                className="truncate text-xs font-medium"
                style={{ maxWidth: '140px' }}
                title={`${getTaskTypeName(task.taskType)}${task.name ? `: ${task.name}` : ''}${task.serverId ? ` - ${task.serverId}` : ''}`}
              >
                {task.name || getTaskTypeName(task.taskType)}
                {task.serverId && (
                  <span className="text-gray-400 ml-1">- {task.serverId}</span>
                )}
              </Text>
            </div>

            {isActive && (
              <div className="mt-1">
                {task.progress !== null ? (
                  <Progress
                    percent={task.progress}
                    size="small"
                    strokeColor={task.status === 'pending' ? '#d9d9d9' : '#1677ff'}
                    showInfo={false}
                    className="mb-0.5"
                  />
                ) : (
                  <div className="flex items-center gap-1.5 mb-0.5">
                    <LoadingOutlined spin className="text-blue-500 text-xs" />
                    <Text className="text-xs text-gray-400">处理中...</Text>
                  </div>
                )}
                <Text className="text-xs text-gray-500 truncate block" title={task.message}>
                  {task.message || (task.status === 'pending' ? '等待执行...' : '处理中...')}
                </Text>
              </div>
            )}

            {task.status === 'completed' && (
              <Text type="success" className="text-xs">已完成</Text>
            )}

            {task.status === 'failed' && (
              <Text type="danger" className="text-xs truncate block" title={task.error}>
                {task.error || '任务失败'}
              </Text>
            )}

            {task.status === 'cancelled' && (
              <Text type="secondary" className="text-xs">已取消</Text>
            )}
          </div>
        </Popover>
      </div>

      {(canCancel || !isActive) && (
        <Tooltip title={canCancel ? '取消任务' : '移除任务'}>
          <Button
            size="small"
            type="text"
            icon={canCancel ? <StopOutlined /> : <CloseOutlined />}
            onClick={handleAction}
            className="flex-shrink-0"
          />
        </Tooltip>
      )}
    </div>
  )
}

export default BackgroundTaskItem
