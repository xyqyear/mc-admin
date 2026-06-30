import React from 'react'
import {
  FileArchive,
  Hammer,
  Ban,
  X,
  CheckCircle2,
  AlertCircle,
  Loader2,
  Clock,
  Wrench,
  Eraser,
} from 'lucide-react'

import { Progress } from '@/components/ui/progress'
import { Button } from '@/components/ui/button'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import type {
  BackgroundTask,
  BackgroundTaskType,
} from '@/stores/useBackgroundTaskStore'

interface BackgroundTaskItemProps {
  task: BackgroundTask
  onCancel: (taskId: string) => void
  onRemove: (taskId: string) => void
}

const getTaskTypeIcon = (taskType: BackgroundTaskType) => {
  switch (taskType) {
    case 'archive_create':
    case 'archive_extract':
      return <FileArchive className="h-3.5 w-3.5" />
    case 'file_ownership_repair':
      return <Wrench className="h-3.5 w-3.5" />
    case 'server_rebuild':
      return <Hammer className="h-3.5 w-3.5" />
    case 'chunk_prune_preview':
    case 'chunk_prune_apply':
      return <Eraser className="h-3.5 w-3.5" />
    default:
      return <Loader2 className="h-3.5 w-3.5 animate-spin" />
  }
}

const getTaskTypeName = (taskType: BackgroundTaskType): string => {
  switch (taskType) {
    case 'archive_create':
      return '创建压缩包'
    case 'archive_extract':
      return '解压文件'
    case 'file_ownership_repair':
      return '修复文件所有权'
    case 'server_rebuild':
      return '重建服务器'
    case 'chunk_prune_preview':
      return '区块清理预览'
    case 'chunk_prune_apply':
      return '区块清理删除'
    default:
      return '未知任务'
  }
}

const getStatusIcon = (status: BackgroundTask['status']) => {
  switch (status) {
    case 'pending':
      return <Clock className="h-3.5 w-3.5 text-gray-500" />
    case 'running':
      return <Loader2 className="h-3.5 w-3.5 text-blue-500 animate-spin" />
    case 'completed':
      return <CheckCircle2 className="h-3.5 w-3.5 text-green-500" />
    case 'failed':
      return <AlertCircle className="h-3.5 w-3.5 text-red-500" />
    case 'cancelled':
      return <Ban className="h-3.5 w-3.5 text-gray-500" />
    default:
      return <Loader2 className="h-3.5 w-3.5" />
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

const truncatePath = (path: string, maxLength: number = 20): string => {
  if (path.length <= maxLength) return path
  return '...' + path.slice(-(maxLength - 3))
}

const getTaskDisplayName = (task: BackgroundTask): string => {
  if (task.taskType === 'archive_create' && task.name) {
    return `压缩 ${truncatePath(task.name)}`
  }
  if (task.taskType === 'archive_extract' && task.name) {
    return `解压 ${truncatePath(task.name)}`
  }
  if (task.taskType === 'file_ownership_repair' && task.name) {
    return `修复 ${truncatePath(task.name)}`
  }
  if (task.taskType === 'chunk_prune_preview' && task.name) {
    return task.name
  }
  if (task.taskType === 'chunk_prune_apply' && task.name) {
    return task.name
  }
  return task.name || getTaskTypeName(task.taskType)
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
    <div className="space-y-2 min-w-48 text-xs">
      <div>
        <strong>任务类型：</strong>
        {getTaskTypeName(task.taskType)}
      </div>
      {task.name && (
        <div>
          <strong>名称：</strong>
          {task.name}
        </div>
      )}
      {task.serverId && (
        <div>
          <strong>服务器：</strong>
          {task.serverId}
        </div>
      )}
      <div>
        <strong>状态：</strong>
        {getStatusText(task.status)}
      </div>
      <div>
        <strong>用时：</strong>
        {getElapsedTime(task)}
      </div>
      {task.message && (
        <div>
          <strong>进度：</strong>
          <span className="break-all">{task.message}</span>
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

  const handleAction = () => {
    if (canCancel) {
      onCancel(task.taskId)
    } else if (!isActive) {
      onRemove(task.taskId)
    }
  }

  return (
    <div className="flex items-center gap-2 p-2 hover:bg-muted/50 rounded transition-colors">
      <span className="flex shrink-0 w-5 justify-center">
        {getStatusIcon(task.status)}
      </span>

      <div className="flex-1 min-w-0">
        <Popover>
          <PopoverTrigger className="w-full text-left cursor-pointer">
            <div className="flex items-center gap-1.5">
              <span className="shrink-0 text-muted-foreground">
                {getTaskTypeIcon(task.taskType)}
              </span>
              <span
                className="truncate text-xs font-medium max-w-45"
                title={task.name || getTaskTypeName(task.taskType)}
              >
                {getTaskDisplayName(task)}
              </span>
            </div>

            {isActive && (
              <div className="mt-1">
                {task.progress !== null ? (
                  <Progress
                    value={task.progress ?? 0}
                    className="h-1 mb-0.5"
                  />
                ) : (
                  <div className="flex items-center gap-1.5 mb-0.5">
                    <Loader2 className="h-3 w-3 animate-spin text-blue-500" />
                    <span className="text-xs text-muted-foreground">处理中...</span>
                  </div>
                )}
                <span
                  className="block truncate text-xs text-muted-foreground"
                  title={task.message}
                >
                  {task.message ||
                    (task.status === 'pending' ? '等待执行...' : '处理中...')}
                </span>
              </div>
            )}

            {task.status === 'completed' && (
              <span className="text-xs text-green-600">已完成</span>
            )}

            {task.status === 'failed' && (
              <span
                className="block truncate text-xs text-destructive"
                title={task.error}
              >
                {task.error || '任务失败'}
              </span>
            )}

            {task.status === 'cancelled' && (
              <span className="text-xs text-muted-foreground">已取消</span>
            )}
          </PopoverTrigger>
          <PopoverContent side="left" className="w-auto">
            <div className="mb-2 text-sm font-semibold">任务详情</div>
            {taskInfo}
          </PopoverContent>
        </Popover>
      </div>

      {(canCancel || !isActive) && (
        <Tooltip>
          <TooltipTrigger
            className="inline-flex"
            render={
              <Button
                variant="ghost"
                size="icon-sm"
                onClick={handleAction}
                className="shrink-0"
              />
            }
          >
            {canCancel ? <Ban className="h-3.5 w-3.5" /> : <X className="h-3.5 w-3.5" />}
          </TooltipTrigger>
          <TooltipContent side="left">
            {canCancel ? '取消任务' : '移除任务'}
          </TooltipContent>
        </Tooltip>
      )}
    </div>
  )
}

export default BackgroundTaskItem
