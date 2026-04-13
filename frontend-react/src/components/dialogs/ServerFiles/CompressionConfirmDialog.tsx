import React from 'react'
import { toast } from 'sonner'
import { Archive, Folder, Server, Loader2 } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Alert, AlertTitle, AlertDescription } from '@/components/ui/alert'
import { Progress } from '@/components/ui/progress'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import type { FileItem } from '@/types/Server'
import type { BackgroundTask } from '@/stores/useBackgroundTaskStore'

interface CompressionConfirmDialogProps {
  open: boolean
  onCancel: () => void
  onOk: () => void
  confirmLoading: boolean
  task?: BackgroundTask | null
  selectedFile?: FileItem | null
  currentPath: string
  compressionType: 'file' | 'folder' | 'server'
  serverName?: string
}

const CompressionConfirmDialog: React.FC<CompressionConfirmDialogProps> = ({
  open,
  onCancel,
  onOk,
  confirmLoading,
  task,
  selectedFile,
  currentPath,
  compressionType,
  serverName = ''
}) => {
  const isTaskRunning = task && (task.status === 'running' || task.status === 'pending')

  const handleClose = () => {
    if (isTaskRunning) {
      toast.info('压缩进度可在右下角任务管理中查看')
    }
    onCancel()
  }

  const getCompressionDescription = () => {
    switch (compressionType) {
      case 'file':
        return `将压缩文件 "${selectedFile?.name}" 为压缩包`
      case 'folder':
        return selectedFile
          ? `将压缩文件夹 "${selectedFile.name}" 为压缩包`
          : `将压缩当前目录 "${currentPath}" 下的所有内容为压缩包`
      case 'server':
        return `将压缩整个服务器 "${serverName}" 的所有文件为压缩包`
      default:
        return ''
    }
  }

  const getCompressionIcon = () => {
    switch (compressionType) {
      case 'file':
        return <Archive className="h-5 w-5 text-blue-500" />
      case 'folder':
        return <Folder className="h-5 w-5 text-orange-500" />
      case 'server':
        return <Server className="h-5 w-5 text-green-500" />
      default:
        return <Archive className="h-5 w-5 text-blue-500" />
    }
  }

  const getCompressionTitle = () => {
    switch (compressionType) {
      case 'file':
        return '压缩单个文件'
      case 'folder':
        return '压缩文件夹'
      case 'server':
        return '压缩整个服务器'
      default:
        return '创建压缩包'
    }
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !o && handleClose()}>
      <DialogContent className="sm:max-w-125">
        <DialogHeader>
          <DialogTitle>创建压缩包</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <Alert>
            <AlertTitle>压缩包创建</AlertTitle>
            <AlertDescription>
              确认要创建压缩包吗？压缩完成后会自动保存到压缩包管理中。
            </AlertDescription>
          </Alert>

          <div className="bg-muted p-4 rounded-md border">
            <div className="flex items-center gap-3 mb-2">
              {getCompressionIcon()}
              <span className="font-medium text-lg">{getCompressionTitle()}</span>
            </div>
            <div className="text-muted-foreground ml-8">
              {getCompressionDescription()}
            </div>
          </div>

          <Alert>
            <AlertTitle>注意事项</AlertTitle>
            <AlertDescription>
              压缩过程可能需要一些时间，特别是在压缩整个服务器时。压缩完成后压缩包将出现在压缩包管理界面。
            </AlertDescription>
          </Alert>

          {isTaskRunning && (
            <div className="space-y-2">
              <Progress value={task.progress ?? 0} />
              <div className="text-muted-foreground text-sm">
                {task.progress ?? 0}% - {task.message || '正在压缩...'}
              </div>
            </div>
          )}

          {(confirmLoading && !isTaskRunning) && (
            <Alert>
              <AlertTitle>正在提交任务...</AlertTitle>
              <AlertDescription>
                正在提交压缩任务，请稍候。
              </AlertDescription>
            </Alert>
          )}
        </div>
        <DialogFooter>
          <Button
            variant="outline"
            onClick={handleClose}
            disabled={confirmLoading && !isTaskRunning}
          >
            取消
          </Button>
          <Button
            onClick={onOk}
            disabled={confirmLoading || !!isTaskRunning}
          >
            {confirmLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            {confirmLoading || isTaskRunning ? '压缩中...' : '开始压缩'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export default CompressionConfirmDialog
