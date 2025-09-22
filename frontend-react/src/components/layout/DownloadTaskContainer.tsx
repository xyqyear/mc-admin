import React from 'react'
import { Card, Progress, Button, Typography, Space, Tooltip, Popover } from 'antd'
import {
  DownloadOutlined,
  CloseOutlined,
  DeleteOutlined,
  CheckCircleOutlined,
  ExclamationCircleOutlined,
  StopOutlined,
} from '@ant-design/icons'
import { useDownloadTasks, useDownloadActions, type DownloadTask } from '@/stores/useDownloadStore'
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
    <div className="space-y-2">
      <div>
        <Text strong>文件名：</Text>
        <Text>{task.fileName}</Text>
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
          <Text type="danger">{task.error}</Text>
        </div>
      )}
    </div>
  )

  return (
    <div className="flex items-center space-x-2 p-2 hover:bg-gray-50 rounded">
      {getStatusIcon()}

      <div className="flex-1 min-w-0">
        <Popover content={taskInfo} title="下载详情" placement="right">
          <div className="cursor-pointer">
            <Text
              className="block truncate text-xs font-medium"
              style={{ maxWidth: '120px' }}
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
                  className="mb-1"
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

const DownloadTaskContainer: React.FC = () => {
  const allTasks = useDownloadTasks()
  const { clearCompletedTasks } = useDownloadActions()

  // 只显示正在下载的任务和最近完成/失败的任务
  const visibleTasks = allTasks.filter(task =>
    task.status === 'downloading' ||
    (task.endTime && Date.now() - task.endTime < 5 * 60 * 1000) // 5分钟内完成的任务
  )

  // 如果没有可见任务，不显示容器
  if (visibleTasks.length === 0) {
    return null
  }

  return (
    <div className="border-t border-gray-200 bg-white">
      <Card
        size="small"
        title={
          <Space>
            <DownloadOutlined />
            <span className="text-sm">下载任务 ({visibleTasks.length})</span>
          </Space>
        }
        extra={
          <Space>
            <Tooltip title="清除已完成的任务">
              <Button
                size="small"
                type="text"
                icon={<DeleteOutlined />}
                onClick={clearCompletedTasks}
              />
            </Tooltip>
          </Space>
        }
        className="mx-2 mb-2"
        styles={{
          header: { padding: '8px 12px', minHeight: 'auto' },
          body: { padding: '0' },
        }}
      >
        <div className="max-h-40 overflow-y-auto">
          {visibleTasks.map(task => (
            <DownloadTaskItem key={task.id} task={task} />
          ))}
        </div>
      </Card>
    </div>
  )
}

export default DownloadTaskContainer