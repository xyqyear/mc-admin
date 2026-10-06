import React from 'react'
import {
  Download,
  X,
  CheckCircle2,
  AlertCircle,
  Ban,
} from 'lucide-react'

import { Progress } from '@/shared/ui/progress'
import { Button } from '@/shared/ui/button'
import { Popover, PopoverContent, PopoverTrigger } from '@/shared/ui/popover'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/shared/ui/tooltip'
import {
  useDownloadActions,
  type DownloadTask,
} from '@/features/tasks/downloadStore'
import { formatFileSize } from '@/shared/utils/formatUtils'

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
    if (task.totalFiles !== undefined) {
      return task.listingComplete
        ? `${task.completedFiles ?? 0} / ${task.totalFiles} 个文件`
        : `已保存 ${task.completedFiles ?? 0} 个，正在读取清单`
    }
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
      {task.destination && (
        <div>
          <strong>保存位置：</strong>
          <span className="break-all">{task.destination}</span>
        </div>
      )}
      {task.totalFiles !== undefined && (
        <div>
          <strong>文件：</strong>
          已保存 {task.completedFiles ?? 0} 个，失败 {task.failedFiles ?? 0} 个
          {task.listingComplete && `，共 ${task.totalFiles} 个`}
        </div>
      )}
      {task.size !== undefined && (
        <div>
          <strong>传输：</strong>
          {formatFileSize(task.downloadedSize ?? 0)} / {formatFileSize(task.size)}
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
      {!!task.warningCount && (
        <div>
          <strong>文件名调整：</strong>
          {task.warningCount} 项
          <div className="mt-1 max-h-36 overflow-auto space-y-1 max-w-80">
            {task.warnings?.map((warning) => (
              <div key={warning.path} className="break-all">
                {warning.path} → {warning.destination}
                <div className="text-muted-foreground">{warning.reason}</div>
              </div>
            ))}
          </div>
          {task.warningCount > (task.warnings?.length ?? 0) && (
            <div className="text-muted-foreground">仅展示前 {task.warnings?.length ?? 0} 项</div>
          )}
        </div>
      )}
      {!!task.failures?.length && (
        <div>
          <strong>失败文件：</strong>
          <div className="mt-1 max-h-36 overflow-auto space-y-1 max-w-80">
            {task.failures.map((failure) => (
              <div key={failure.path} className="break-all text-destructive">
                {failure.path}：{failure.error}
              </div>
            ))}
          </div>
          {(task.failedFiles ?? 0) > task.failures.length && (
            <div className="text-muted-foreground">仅展示前 {task.failures.length} 项</div>
          )}
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
              <span className="text-xs text-green-600">
                {task.totalFiles !== undefined ? `已保存 ${task.completedFiles ?? 0} 个文件` : '下载完成'}
              </span>
            )}

            {task.status === 'error' && (
              <span className="text-xs text-destructive">
                {task.totalFiles !== undefined
                  ? task.failedFiles
                    ? `已保存 ${task.completedFiles ?? 0} 个，失败 ${task.failedFiles} 个`
                    : `下载中断，已保存 ${task.completedFiles ?? 0} 个`
                  : '下载失败'}
              </span>
            )}

            {task.status === 'cancelled' && (
              <span className="text-xs text-muted-foreground">
                {task.totalFiles !== undefined ? `已取消，保留 ${task.completedFiles ?? 0} 个文件` : '已取消'}
              </span>
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
