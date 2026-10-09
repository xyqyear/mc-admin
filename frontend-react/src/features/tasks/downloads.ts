import { getErrorMessage } from '@/shared/http/api'
import { useDownloadActions } from '@/features/tasks/downloadStore'
import type { DownloadFailure, DownloadPathWarning } from '@/features/tasks/downloadStore'
import { toast } from 'sonner'

export const triggerBrowserDownload = (blob: Blob, filename: string): void => {
  const url = window.URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  window.URL.revokeObjectURL(url)
}

export interface DownloadProgress {
  loaded: number
  total: number
  percent: number
  speed?: number
}

export type DownloadFunction = (
  onProgress?: (progress: DownloadProgress) => void,
  signal?: AbortSignal
) => Promise<Blob>

export interface DownloadOptions {
  filename: string
  serverId?: string
  onSuccess?: () => void
  onError?: (error: any) => void
}

export interface ManagedDownloadProgress {
  downloadedSize?: number
  size?: number
  progress?: number
  speed?: number
  totalFiles?: number
  completedFiles?: number
  failedFiles?: number
  listingComplete?: boolean
  destination?: string
  failures?: DownloadFailure[]
  warnings?: DownloadPathWarning[]
  warningCount?: number
}

export interface ManagedDownloadResult extends ManagedDownloadProgress {
  failedFiles: number
}

export type ManagedDownloadFunction = (
  report: (progress: ManagedDownloadProgress) => void,
  signal: AbortSignal,
) => Promise<ManagedDownloadResult>

export const useDownloadManager = () => {
  const { addTask, updateTask } = useDownloadActions()

  const executeDownload = async (
    downloadFn: DownloadFunction,
    options: DownloadOptions
  ): Promise<void> => {
    const { filename, serverId, onSuccess, onError } = options

    const abortController = new AbortController()

    const taskId = addTask({
      fileName: filename,
      serverId: serverId,
      status: 'downloading',
      progress: 0,
      abortController,
    })

    try {
      const blob = await downloadFn(
        (progress) => {
          updateTask(taskId, {
            progress: progress.percent,
            downloadedSize: progress.loaded,
            size: progress.total,
            speed: progress.speed,
          })
        },
        abortController.signal
      )

      triggerBrowserDownload(blob, filename)

      updateTask(taskId, {
        status: 'completed',
        progress: 100,
        endTime: Date.now(),
      })

      toast.success('下载完成')
      onSuccess?.()
    } catch (error: any) {
      // Axios reports user-cancelled requests as ERR_CANCELED rather than AbortError.
      if (error.name === 'AbortError' || error.code === 'ERR_CANCELED') {
        updateTask(taskId, {
          status: 'cancelled',
          endTime: Date.now(),
        })
        toast.info('下载已取消')
      } else {
        updateTask(taskId, {
          status: 'error',
          error: getErrorMessage(error) || '下载失败',
          endTime: Date.now(),
        })
        toast.error(getErrorMessage(error) || '下载失败')
        onError?.(error)
      }
    }
  }

  const executeManagedDownload = async (
    downloadFn: ManagedDownloadFunction,
    options: DownloadOptions,
  ): Promise<void> => {
    const abortController = new AbortController()
    const taskId = addTask({
      fileName: options.filename,
      serverId: options.serverId,
      status: 'downloading',
      progress: 0,
      completedFiles: 0,
      failedFiles: 0,
      totalFiles: 0,
      listingComplete: false,
      abortController,
    })

    try {
      const result = await downloadFn((progress) => updateTask(taskId, progress), abortController.signal)
      abortController.signal.throwIfAborted()
      updateTask(taskId, {
        ...result,
        status: result.failedFiles ? 'error' : 'completed',
        error: result.failedFiles ? `${result.failedFiles} 个文件下载失败，已完成的文件已保留` : undefined,
        progress: result.failedFiles ? result.progress ?? 0 : 100,
        endTime: Date.now(),
        abortController: undefined,
      })
      if (result.failedFiles) {
        toast.error(`${result.failedFiles} 个文件下载失败，详情见任务中心`)
      } else {
        toast.success('下载完成')
        options.onSuccess?.()
      }
    } catch (error: unknown) {
      const cancelled = abortController.signal.aborted
      updateTask(taskId, {
        status: cancelled ? 'cancelled' : 'error',
        error: cancelled ? undefined : getErrorMessage(error, '下载失败'),
        endTime: Date.now(),
        abortController: undefined,
      })
      if (cancelled) {
        toast.info('下载已取消，已完成的文件已保留')
      } else {
        toast.error(getErrorMessage(error, '下载失败'))
        options.onError?.(error)
      }
    }
  }

  return {
    executeDownload,
    executeManagedDownload,
  }
}
