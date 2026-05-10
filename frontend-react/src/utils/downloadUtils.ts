import { useDownloadActions } from '@/stores/useDownloadStore'
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
          error: error.response?.data?.detail || error.message || '下载失败',
          endTime: Date.now(),
        })
        toast.error(error.response?.data?.detail || error.message || '下载失败')
        onError?.(error)
      }
    }
  }

  return {
    executeDownload,
  }
}

export const simpleDownload = (blob: Blob, filename: string): void => {
  triggerBrowserDownload(blob, filename)
}