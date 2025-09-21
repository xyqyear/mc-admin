import { useDownloadActions } from '@/stores/useDownloadStore'
import { App } from 'antd'

/**
 * 创建浏览器下载链接并触发下载
 */
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

/**
 * 下载进度回调接口
 */
export interface DownloadProgress {
  loaded: number
  total: number
  percent: number
  speed?: number
}

/**
 * 下载函数类型
 */
export type DownloadFunction = (
  onProgress?: (progress: DownloadProgress) => void,
  signal?: AbortSignal
) => Promise<Blob>

/**
 * 下载选项
 */
export interface DownloadOptions {
  filename: string
  serverId?: string
  onSuccess?: () => void
  onError?: (error: any) => void
}

/**
 * 通用的带进度追踪的下载管理器
 */
export const useDownloadManager = () => {
  const { addTask, updateTask } = useDownloadActions()
  const { message } = App.useApp()

  /**
   * 执行带进度追踪的下载
   */
  const executeDownload = async (
    downloadFn: DownloadFunction,
    options: DownloadOptions
  ): Promise<void> => {
    const { filename, serverId, onSuccess, onError } = options

    // 创建AbortController用于取消下载
    const abortController = new AbortController()

    // 添加下载任务到状态管理
    const taskId = addTask({
      fileName: filename,
      serverId: serverId,
      status: 'downloading',
      progress: 0,
      abortController,
    })

    try {
      // 执行下载
      const blob = await downloadFn(
        (progress) => {
          // 更新下载进度
          updateTask(taskId, {
            progress: progress.percent,
            downloadedSize: progress.loaded,
            size: progress.total,
            speed: progress.speed,
          })
        },
        abortController.signal
      )

      // 下载完成，触发浏览器下载
      triggerBrowserDownload(blob, filename)

      // 更新任务状态为完成
      updateTask(taskId, {
        status: 'completed',
        progress: 100,
        endTime: Date.now(),
      })

      message.success('下载完成')
      onSuccess?.()
    } catch (error: any) {
      // 检查是否为用户取消
      if (error.name === 'AbortError' || error.code === 'ERR_CANCELED') {
        updateTask(taskId, {
          status: 'cancelled',
          endTime: Date.now(),
        })
        message.info('下载已取消')
      } else {
        updateTask(taskId, {
          status: 'error',
          error: error.response?.data?.detail || error.message || '下载失败',
          endTime: Date.now(),
        })
        message.error(error.response?.data?.detail || error.message || '下载失败')
        onError?.(error)
      }
    }
  }

  return {
    executeDownload,
  }
}

/**
 * 简单的下载函数（不带进度追踪）
 * 用于向后兼容或简单的下载场景
 */
export const simpleDownload = (blob: Blob, filename: string): void => {
  triggerBrowserDownload(blob, filename)
}