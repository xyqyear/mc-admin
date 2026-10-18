import React from 'react'
import { Inbox, Trash2 } from 'lucide-react'

import { Button } from '@/shared/ui/button'
import { Separator } from '@/shared/ui/separator'
import { useQueryClient } from '@tanstack/react-query'
import { useTaskFeed, retryTaskObservation, useTasks } from '@/features/tasks/queries';
import { useCancelTask, useDeleteTask, useClearCompletedTasks } from '@/features/tasks/commands';
import BackgroundTaskItem from '@/features/tasks/ui/BackgroundTaskItem'
import type { BackgroundTask } from '@/features/tasks/contracts'

const BackgroundTaskList: React.FC = () => {
  const { data, isLoading, isError, error, refetch, isFetching } = useTasks()
  const feed = useTaskFeed()
  const client = useQueryClient()
  const retry = () => { retryTaskObservation(client); void refetch() }
  const cancelTask = useCancelTask()
  const deleteTask = useDeleteTask()
  const clearCompleted = useClearCompletedTasks()

  const tasks = [...(data?.tasks || [])].sort((a, b) => b.createdAt - a.createdAt)

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

  if (isError && !data) return <div role="alert" className="space-y-2 p-4 text-sm"><p>无法读取后台任务：{error.message}</p><Button variant="outline" size="sm" onClick={retry} disabled={isFetching}>重试连接</Button></div>

  if (isLoading) {
    return (
      <div className="p-4 text-center text-sm text-muted-foreground">加载中...</div>
    )
  }

  const connection = !feed.connected ? <div role="status" className="space-y-2 border-b p-3 text-xs text-muted-foreground"><p>{feed.tasks === undefined ? '尚未建立任务实时连接，当前状态可能不完整。' : '任务连接已中断，显示的是上次收到的状态。'}</p><Button size="sm" variant="outline" onClick={retry}>重试连接</Button></div> : null

  if (tasks.length === 0) {
    return (
      <div>{connection}<div className="flex flex-col items-center justify-center p-6 text-muted-foreground">
        <Inbox className="mb-2 h-8 w-8 opacity-50" />
        <p className="text-xs">{feed.connected || data ? '暂无后台任务' : '任务状态尚未确认'}</p>
      </div></div>
    )
  }

  return (
    <div className="max-h-80 overflow-y-auto">
      {connection}
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
              actionPending={(cancelTask.isPending && cancelTask.variables === task.taskId) || (deleteTask.isPending && deleteTask.variables === task.taskId) || clearCompleted.isPending}
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
              disabled={clearCompleted.isPending}
              className="h-6 px-2 text-xs"
            >
              <Trash2 className="mr-1 h-3 w-3" />
              {clearCompleted.isPending ? '清除中…' : '清除'}
            </Button>
          </div>
          {recentCompletedTasks.map((task: BackgroundTask) => (
            <BackgroundTaskItem
              key={task.taskId}
              task={task}
              onCancel={handleCancel}
              onRemove={handleRemove}
              actionPending={(cancelTask.isPending && cancelTask.variables === task.taskId) || (deleteTask.isPending && deleteTask.variables === task.taskId) || clearCompleted.isPending}
            />
          ))}
        </div>
      )}
    </div>
  )
}

export default BackgroundTaskList
