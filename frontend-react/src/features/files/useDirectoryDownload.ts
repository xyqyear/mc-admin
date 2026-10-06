import { toast } from 'sonner'
import { useDownloadManager } from '@/features/tasks/downloads'
import {
  executeDirectoryDownload,
  getLocalDownloadError,
  type DirectoryDownloadOptions,
} from '@/features/files/directoryDownload'

interface DirectoryPickerWindow extends Window {
  showDirectoryPicker?: (options: { mode: 'readwrite' }) => Promise<FileSystemDirectoryHandle>
}

export const getDirectoryDownloadSupport = (): { supported: boolean; reason?: string } => {
  const browser = window as DirectoryPickerWindow
  const hasPicker = typeof browser.showDirectoryPicker === 'function'
  const hasWriter = typeof FileSystemFileHandle !== 'undefined' && typeof FileSystemFileHandle.prototype.createWritable === 'function'
  const chromeOrEdge = /\b(?:Chrome|Edg)\//.test(navigator.userAgent)
  if (!window.isSecureContext && (hasPicker || chromeOrEdge)) {
    return { supported: false, reason: '此功能需要通过 HTTPS 或 localhost 访问。' }
  }
  if (!hasPicker || !hasWriter || !window.isSecureContext) {
    return { supported: false, reason: '当前浏览器不支持直接下载到文件夹，仅支持 Chrome 和 Edge。' }
  }
  return { supported: true }
}

export const useDirectoryDownload = (serverId: string) => {
  const support = getDirectoryDownloadSupport()
  const { executeManagedDownload } = useDownloadManager()

  const downloadToDirectory = async (options: DirectoryDownloadOptions): Promise<void> => {
    if (!support.supported) {
      toast.error(support.reason)
      return
    }
    const accepted = { ...options, paths: [...options.paths] }
    let selected: FileSystemDirectoryHandle
    try {
      selected = await (window as DirectoryPickerWindow).showDirectoryPicker!({ mode: 'readwrite' })
    } catch (error) {
      if (error instanceof DOMException && error.name === 'AbortError') return
      toast.error(getLocalDownloadError(error))
      return
    }
    await executeManagedDownload(
      (report, signal) => executeDirectoryDownload(serverId, selected, accepted, report, signal),
      { serverId, filename: `文件夹下载（${accepted.paths.length} 个目标）` },
    )
  }

  return { ...support, downloadToDirectory }
}
