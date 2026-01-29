import React from 'react'
import { Progress, Button, Typography, Tooltip, Popover } from 'antd'
import {
  DownloadOutlined,
  CloseOutlined,
  CheckCircleOutlined,
  ExclamationCircleOutlined,
  StopOutlined,
} from '@ant-design/icons'
import { useDownloadActions, type DownloadTask } from '@/stores/useDownloadStore'
import { formatFileSize } from '@/utils/formatUtils'

const { Text } = Typography

interface DownloadTaskItemProps {
  task: DownloadTask
}

const DownloadTaskItem: React.FC<DownloadTaskItemProps> = ({ task }) => {
  const { cancelTask, removeTask } = useDownloadActions()

  const getStatusIcon = () => {
    switch (task.status) {
      case 'downloading':
        return <DownloadOutlined className="text-blue-500 animate-pulse" />
      case 'completed':
        return <CheckCircleOutlined className="text-green-500" />
      case 'error':
        return <ExclamationCircleOutlined className="text-red-500" />
      case 'cancelled':
        return <StopOutlined className="text-gray-500" />
      default:
        return <DownloadOutlined />
    }
  }

  const getStatusColor = () => {
    switch (task.status) {
      case 'downloading':
        return '#1677ff'
      case 'completed':
        return '#52c41a'
      case 'error':
        return '#ff4d4f'
      case 'cancelled':
        return '#d9d9d9'
      default:
        return '#1677ff'
    }
  }

  const formatSpeed = (bytesPerSecond?: number) => {
    if (!bytesPerSecond) return ''
    if (bytesPerSecond < 1024) return `${bytesPerSecond.toFixed(0)} B/s`
    if (bytesPerSecond < 1024 * 1024) return `${(bytesPerSecond / 1024).toFixed(1)} KB/s`
    return `${(bytesPerSecond / (1024 * 1024)).toFixed(1)} MB/s`
  }

  const getElapsedTime = () => {
    const elapsed = (task.endTime || Date.now()) - task.startTime
    const seconds = Math.floor(elapsed / 1000)
    if (seconds < 60) return `${seconds}秒`
    const minutes = Math.floor(seconds / 60)
    return `${minutes}分${seconds % 60}秒`
  }

  const handleCancel = () => {
    if (task.status === 'downloading') {
      cancelTask(task.id)
    } else {
      removeTask(task.id)
    }
  }

  const getProgressInfo = () => {
    if (task.size && task.downloadedSize) {
      return `${formatFileSize(task.downloadedSize)} / ${formatFileSize(task.size)}`
    }
    if (task.progress > 0) {
      return `${task.progress.toFixed(1)}%`
    }
    return ''
  }

  const taskInfo = (
    <div className="space-y-2 min-w-48">
      <div>
        <Text strong>文件名：</Text>
        <Text className="break-all">{task.fileName}</Text>
      </div>
      {task.serverId && (
        <div>
          <Text strong>服务器：</Text>
          <Text>{task.serverId}</Text>
        </div>
      )}
      <div>
        <Text strong>状态：</Text>
        <Text>{task.status === 'downloading' ? '下载中' :
          task.status === 'completed' ? '已完成' :
            task.status === 'error' ? '出错' : '已取消'}</Text>
      </div>
      <div>
        <Text strong>用时：</Text>
        <Text>{getElapsedTime()}</Text>
      </div>
      {task.speed && task.status === 'downloading' && (
        <div>
          <Text strong>速度：</Text>
          <Text>{formatSpeed(task.speed)}</Text>
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

  return (
    <div className="flex items-center gap-2 p-2 hover:bg-gray-50 rounded transition-colors">
      <span className="flex-shrink-0 w-5 text-center">
        {getStatusIcon()}
      </span>

      <div className="flex-1 min-w-0">
        <Popover content={taskInfo} title="下载详情" placement="left">
          <div className="cursor-pointer">
            <Text
              className="block truncate text-xs font-medium"
              style={{ maxWidth: '160px' }}
              title={task.fileName}
            >
              {task.fileName}
            </Text>

            {task.status === 'downloading' && (
              <div className="mt-1">
                <Progress
                  percent={task.progress}
                  size="small"
                  strokeColor={getStatusColor()}
                  showInfo={false}
                  className="mb-0.5"
                />
                <div className="flex justify-between text-xs text-gray-500">
                  <span>{getProgressInfo()}</span>
                  {task.speed && <span>{formatSpeed(task.speed)}</span>}
                </div>
              </div>
            )}

            {task.status === 'completed' && (
              <Text type="success" className="text-xs">下载完成</Text>
            )}

            {task.status === 'error' && (
              <Text type="danger" className="text-xs">下载失败</Text>
            )}

            {task.status === 'cancelled' && (
              <Text type="secondary" className="text-xs">已取消</Text>
            )}
          </div>
        </Popover>
      </div>

      <Tooltip title={task.status === 'downloading' ? '取消下载' : '移除任务'}>
        <Button
          size="small"
          type="text"
          icon={task.status === 'downloading' ? <StopOutlined /> : <CloseOutlined />}
          onClick={handleCancel}
          className="flex-shrink-0"
        />
      </Tooltip>
    </div>
  )
}

export default DownloadTaskItem
