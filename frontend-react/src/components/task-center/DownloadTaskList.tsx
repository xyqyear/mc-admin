import React from 'react'
import { Empty, Button, Typography, Divider } from 'antd'
import { DeleteOutlined } from '@ant-design/icons'
import { useDownloadTasks, useDownloadActions, type DownloadTask } from '@/stores/useDownloadStore'
import DownloadTaskItem from './DownloadTaskItem'

const { Text } = Typography

const DownloadTaskList: React.FC = () => {
  const allTasks = useDownloadTasks()
  const { clearCompletedTasks } = useDownloadActions()

  // Separate active and completed tasks
  const activeTasks = allTasks.filter((task) => task.status === 'downloading')
  const completedTasks = allTasks.filter((task) => task.status !== 'downloading')

  // Only show completed tasks from the last 30 minutes
  const recentCompletedTasks = completedTasks.filter((task) => {
    if (!task.endTime) return true
    return Date.now() - task.endTime < 30 * 60 * 1000
  })

  if (allTasks.length === 0) {
    return (
      <div className="p-4">
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description="暂无下载任务"
        />
      </div>
    )
  }

  // If no visible tasks (all completed tasks are older than 30 minutes)
  if (activeTasks.length === 0 && recentCompletedTasks.length === 0) {
    return (
      <div className="p-4">
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description="暂无下载任务"
        />
      </div>
    )
  }

  return (
    <div className="max-h-80 overflow-y-auto">
      {activeTasks.length > 0 && (
        <div>
          <div className="px-3 py-1.5 bg-gray-50">
            <Text strong className="text-xs text-gray-600">
              正在下载 ({activeTasks.length})
            </Text>
          </div>
          {activeTasks.map((task: DownloadTask) => (
            <DownloadTaskItem key={task.id} task={task} />
          ))}
        </div>
      )}

      {recentCompletedTasks.length > 0 && (
        <div>
          {activeTasks.length > 0 && <Divider className="my-1" />}
          <div className="px-3 py-1.5 bg-gray-50 flex items-center justify-between">
            <Text strong className="text-xs text-gray-600">
              已完成 ({recentCompletedTasks.length})
            </Text>
            <Button
              size="small"
              type="text"
              icon={<DeleteOutlined />}
              onClick={clearCompletedTasks}
              className="text-xs"
            >
              清除
            </Button>
          </div>
          {recentCompletedTasks.map((task: DownloadTask) => (
            <DownloadTaskItem key={task.id} task={task} />
          ))}
        </div>
      )}
    </div>
  )
}

export default DownloadTaskList
