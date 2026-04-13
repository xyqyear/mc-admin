import React from 'react'
import { ListTodo } from 'lucide-react'

import { Button } from '@/components/ui/button'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { useTaskCenterStore } from '@/stores/useTaskCenterStore'
import { useTaskQueries } from '@/hooks/queries/base/useTaskQueries'
import { useDownloadTasks } from '@/stores/useDownloadStore'

const TaskCenterTrigger: React.FC = () => {
  const { isOpen, toggleOpen } = useTaskCenterStore()
  const { useActiveTasks } = useTaskQueries()
  const { data: activeTasks } = useActiveTasks()
  const downloadTasks = useDownloadTasks()

  const activeBackgroundCount = activeTasks?.length || 0
  const activeDownloadCount = downloadTasks.filter(
    (t) => t.status === 'downloading'
  ).length
  const totalActiveCount = activeBackgroundCount + activeDownloadCount

  const trigger = (
    <Button
      size="icon"
      variant={isOpen ? 'default' : 'secondary'}
      className="h-12 w-12 rounded-full shadow-lg relative"
      onClick={toggleOpen}
    >
      <ListTodo className="h-5 w-5" />
      {totalActiveCount > 0 && (
        <span className="absolute -top-1 -right-1 flex h-5 min-w-5 items-center justify-center rounded-full bg-destructive px-1 text-xs font-medium text-destructive-foreground">
          {totalActiveCount}
        </span>
      )}
    </Button>
  )

  return (
    <div className="fixed bottom-6 right-6 z-50">
      {isOpen ? (
        trigger
      ) : (
        <Tooltip>
          <TooltipTrigger className="inline-flex" render={trigger} />
          <TooltipContent side="left">任务中心</TooltipContent>
        </Tooltip>
      )}
    </div>
  )
}

export default TaskCenterTrigger
