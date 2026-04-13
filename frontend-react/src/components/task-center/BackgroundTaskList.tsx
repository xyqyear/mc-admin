import React from 'react'
import { Inbox, Trash2 } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Separator } from '@/components/ui/separator'
import { useTaskQueries } from '@/hooks/queries/base/useTaskQueries'
import { useTaskMutations } from '@/hooks/mutations/useTaskMutations'
import BackgroundTaskItem from './BackgroundTaskItem'
import type { BackgroundTask } from '@/stores/useBackgroundTaskStore'

const BackgroundTaskList: React.FC = () => {
  const { useTasks } = useTaskQueries()
  const { useCancelTask, useDeleteTask, useClearCompletedTasks } = useTaskMutations()
  const { data, isLoading } = useTasks()
  const cancelTask = useCancelTask()
  const deleteTask = useDeleteTask()
  const clearCompleted = useClearCompletedTasks()

  const tasks = data?.tasks || []

  const activeTasks = tasks.filter(
    (task) => task.status === 'pending' || task.status === 'running'
  )
  const completedTasks = tasks.filter(
    (task) =>
      task.status === 'completed' ||
      task.status === 'failed' ||
      task.status === 'cancelled'
  )

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
      <div className="p-4 text-center text-sm text-muted-foreground">加载中...</div>
    )
  }

  if (tasks.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center p-6 text-muted-foreground">
        <Inbox className="mb-2 h-8 w-8 opacity-50" />
        <p className="text-xs">暂无后台任务</p>
      </div>
    )
  }

  return (
    <div className="max-h-80 overflow-y-auto">
      {activeTasks.length > 0 && (
        <div>
          <div className="px-3 py-1.5 bg-muted/50">
            <span className="text-xs font-semibold text-muted-foreground">
              正在进行 ({activeTasks.length})
            </span>
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
          {activeTasks.length > 0 && <Separator className="my-1" />}
          <div className="flex items-center justify-between px-3 py-1.5 bg-muted/50">
            <span className="text-xs font-semibold text-muted-foreground">
              已完成 ({recentCompletedTasks.length})
            </span>
            <Button
              variant="ghost"
              size="sm"
              onClick={handleClearCompleted}
              className="h-6 px-2 text-xs"
            >
              <Trash2 className="mr-1 h-3 w-3" />
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
