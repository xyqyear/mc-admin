import React from 'react'
import {
  Download,
  X,
  CheckCircle2,
  AlertCircle,
  Ban,
} from 'lucide-react'

import { Progress } from '@/components/ui/progress'
import { Button } from '@/components/ui/button'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import {
  useDownloadActions,
  type DownloadTask,
} from '@/stores/useDownloadStore'
import { formatFileSize } from '@/utils/formatUtils'

interface DownloadTaskItemProps {
  task: DownloadTask
}

const DownloadTaskItem: React.FC<DownloadTaskItemProps> = ({ task }) => {
  const { cancelTask, removeTask } = useDownloadActions()

  const getStatusIcon = () => {
    switch (task.status) {
      case 'downloading':
        return <Download className="h-3.5 w-3.5 text-blue-500 animate-pulse" />
      case 'completed':
        return <CheckCircle2 className="h-3.5 w-3.5 text-green-500" />
      case 'error':
        return <AlertCircle className="h-3.5 w-3.5 text-red-500" />
      case 'cancelled':
        return <Ban className="h-3.5 w-3.5 text-gray-500" />
      default:
        return <Download className="h-3.5 w-3.5" />
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
    <div className="space-y-2 min-w-48 text-xs">
      <div>
        <strong>文件名：</strong>
        <span className="break-all">{task.fileName}</span>
      </div>
      {task.serverId && (
        <div>
          <strong>服务器：</strong>
          {task.serverId}
        </div>
      )}
      <div>
        <strong>状态：</strong>
        {task.status === 'downloading'
          ? '下载中'
          : task.status === 'completed'
            ? '已完成'
            : task.status === 'error'
              ? '出错'
              : '已取消'}
      </div>
      <div>
        <strong>用时：</strong>
        {getElapsedTime()}
      </div>
      {task.speed && task.status === 'downloading' && (
        <div>
          <strong>速度：</strong>
          {formatSpeed(task.speed)}
        </div>
      )}
      {task.error && (
        <div>
          <strong>错误：</strong>
          <span className="text-destructive break-all">{task.error}</span>
        </div>
      )}
    </div>
  )

  return (
    <div className="flex items-center gap-2 p-2 hover:bg-muted/50 rounded transition-colors">
      <span className="flex shrink-0 w-5 justify-center">{getStatusIcon()}</span>

      <div className="flex-1 min-w-0">
        <Popover>
          <PopoverTrigger className="w-full text-left cursor-pointer">
            <span
              className="block truncate text-xs font-medium max-w-40"
              title={task.fileName}
            >
              {task.fileName}
            </span>

            {task.status === 'downloading' && (
              <div className="mt-1">
                <Progress value={task.progress} className="h-1 mb-0.5" />
                <div className="flex justify-between text-xs text-muted-foreground">
                  <span>{getProgressInfo()}</span>
                  {task.speed && <span>{formatSpeed(task.speed)}</span>}
                </div>
              </div>
            )}

            {task.status === 'completed' && (
              <span className="text-xs text-green-600">下载完成</span>
            )}

            {task.status === 'error' && (
              <span className="text-xs text-destructive">下载失败</span>
            )}

            {task.status === 'cancelled' && (
              <span className="text-xs text-muted-foreground">已取消</span>
            )}
          </PopoverTrigger>
          <PopoverContent side="left" className="w-auto">
            <div className="mb-2 text-sm font-semibold">下载详情</div>
            {taskInfo}
          </PopoverContent>
        </Popover>
      </div>

      <Tooltip>
        <TooltipTrigger
          className="inline-flex"
          render={
            <Button
              variant="ghost"
              size="icon-sm"
              onClick={handleCancel}
              className="shrink-0"
            />
          }
        >
          {task.status === 'downloading' ? (
            <Ban className="h-3.5 w-3.5" />
          ) : (
            <X className="h-3.5 w-3.5" />
          )}
        </TooltipTrigger>
        <TooltipContent side="left">
          {task.status === 'downloading' ? '取消下载' : '移除任务'}
        </TooltipContent>
      </Tooltip>
    </div>
  )
}

export default DownloadTaskItem
