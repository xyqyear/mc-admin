import React from 'react'
import { Inbox, Trash2 } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Separator } from '@/components/ui/separator'
import {
  useDownloadTasks,
  useDownloadActions,
  type DownloadTask,
} from '@/stores/useDownloadStore'
import DownloadTaskItem from './DownloadTaskItem'

const EmptyState = () => (
  <div className="flex flex-col items-center justify-center p-6 text-muted-foreground">
    <Inbox className="mb-2 h-8 w-8 opacity-50" />
    <p className="text-xs">暂无下载任务</p>
  </div>
)

const DownloadTaskList: React.FC = () => {
  const allTasks = useDownloadTasks()
  const { clearCompletedTasks } = useDownloadActions()

  const activeTasks = allTasks.filter((task) => task.status === 'downloading')
  const completedTasks = allTasks.filter((task) => task.status !== 'downloading')

  const recentCompletedTasks = completedTasks.filter((task) => {
    if (!task.endTime) return true
    return Date.now() - task.endTime < 30 * 60 * 1000
  })

  if (allTasks.length === 0) {
    return <EmptyState />
  }

  if (activeTasks.length === 0 && recentCompletedTasks.length === 0) {
    return <EmptyState />
  }

  return (
    <div className="max-h-80 overflow-y-auto">
      {activeTasks.length > 0 && (
        <div>
          <div className="px-3 py-1.5 bg-muted/50">
            <span className="text-xs font-semibold text-muted-foreground">
              正在下载 ({activeTasks.length})
            </span>
          </div>
          {activeTasks.map((task: DownloadTask) => (
            <DownloadTaskItem key={task.id} task={task} />
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
              onClick={clearCompletedTasks}
              className="h-6 px-2 text-xs"
            >
              <Trash2 className="mr-1 h-3 w-3" />
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
