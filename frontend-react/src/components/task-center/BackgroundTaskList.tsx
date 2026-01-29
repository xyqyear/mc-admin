import React from 'react'
import { Empty, Button, Typography, Divider } from 'antd'
import { DeleteOutlined } from '@ant-design/icons'
import { useTaskQueries } from '@/hooks/queries/base/useTaskQueries'
import BackgroundTaskItem from './BackgroundTaskItem'
import type { BackgroundTask } from '@/stores/useBackgroundTaskStore'

const { Text } = Typography

const BackgroundTaskList: React.FC = () => {
  const { useTasks, useCancelTask, useDeleteTask, useClearCompletedTasks } = useTaskQueries()
  const { data, isLoading } = useTasks()
  const cancelTask = useCancelTask()
  const deleteTask = useDeleteTask()
  const clearCompleted = useClearCompletedTasks()

  const tasks = data?.tasks || []

  // Separate active and completed tasks
  const activeTasks = tasks.filter(
    (task) => task.status === 'pending' || task.status === 'running'
  )
  const completedTasks = tasks.filter(
    (task) =>
      task.status === 'completed' ||
      task.status === 'failed' ||
      task.status === 'cancelled'
  )

  // Only show completed tasks from the last 30 minutes
  const recentCompletedTasks = completedTasks.filter((task) => {
    if (!task.endedAt) return true
    return Date.now() - task.endedAt < 30 * 60 * 1000
  })

  const handleCancel = (taskId: string) => {
    cancelTask.mutate(taskId)
  }

  const handleRemove = (taskId: string) => {
    deleteTask.mutate(taskId)
  }

  const handleClearCompleted = () => {
    clearCompleted.mutate()
  }

  if (isLoading) {
    return (
      <div className="p-4 text-center">
        <Text type="secondary">加载中...</Text>
      </div>
    )
  }

  if (tasks.length === 0) {
    return (
      <div className="p-4">
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description="暂无后台任务"
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
              正在进行 ({activeTasks.length})
            </Text>
          </div>
          {activeTasks.map((task: BackgroundTask) => (
            <BackgroundTaskItem
              key={task.taskId}
              task={task}
              onCancel={handleCancel}
              onRemove={handleRemove}
            />
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
              onClick={handleClearCompleted}
              className="text-xs"
            >
              清除
            </Button>
          </div>
          {recentCompletedTasks.map((task: BackgroundTask) => (
            <BackgroundTaskItem
              key={task.taskId}
              task={task}
              onCancel={handleCancel}
              onRemove={handleRemove}
            />
          ))}
        </div>
      )}
    </div>
  )
}

export default BackgroundTaskList
