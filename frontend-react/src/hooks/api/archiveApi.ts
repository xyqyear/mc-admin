import api from '@/utils/api'
import { AxiosRequestConfig } from 'axios'

export interface ArchiveFileItem {
  name: string
  type: 'file' | 'directory'
  size: number
  modified_at: number
  path: string
}

export interface ArchiveFileListResponse {
  items: ArchiveFileItem[]
  current_path: string
}

export interface ArchiveFileContent {
  content: string
}

export interface CreateArchiveFileRequest {
  name: string
  type: 'file' | 'directory'
  path: string
}

export interface RenameArchiveFileRequest {
  old_path: string
  new_name: string
}

export interface UploadProgressEvent {
  loaded: number
  total: number
  progress: number
  bytes?: number
  bytesPerSecond?: number
  estimatedRemaining?: number
}

export interface UploadOptions {
  onUploadProgress?: (progressEvent: UploadProgressEvent) => void
  signal?: AbortSignal
}

export interface CreateArchiveRequest {
  server_id: string
  path?: string | null
}

export interface CreateArchiveResponse {
  task_id: string
}

export const archiveApi = {
  // List archive files
  getArchiveFiles: (path: string = '/'): Promise<ArchiveFileListResponse> =>
    api.get('/archive', { params: { path } }).then((res: any) => res.data),

  // Get file content
  getArchiveFileContent: (path: string): Promise<ArchiveFileContent> =>
    api.get('/archive/content', { params: { path } }).then((res: any) => res.data),

  // Update file content
  updateArchiveFileContent: (path: string, content: string) =>
    api.post('/archive/content', { content }, { params: { path } }).then((res: any) => res.data),

  // Download file with progress tracking and cancellation support
  downloadArchiveFileWithProgress: async (
    path: string,
    onProgress?: (progress: { loaded: number; total: number; percent: number; speed?: number }) => void,
    signal?: AbortSignal
  ): Promise<Blob> => {
    const startTime = Date.now()

    const response = await api.get('/archive/download', {
      params: { path },
      responseType: 'blob',
      timeout: 3600000, // 1 hour timeout for downloads
      signal, // 支持取消
      onDownloadProgress: (progressEvent) => {
        if (onProgress && progressEvent.total) {
          const percent = Math.round((progressEvent.loaded * 100) / progressEvent.total)

          // 计算下载速度
          const currentTime = Date.now()
          const elapsedTime = (currentTime - startTime) / 1000 // 秒
          const speed = elapsedTime > 0 ? progressEvent.loaded / elapsedTime : 0

          onProgress({
            loaded: progressEvent.loaded,
            total: progressEvent.total,
            percent,
            speed,
          })
        }
      },
    });

    return response.data;
  },

  // Upload file
  uploadArchiveFile: (
    path: string,
    file: File,
    allowOverwrite: boolean = false,
    options?: UploadOptions
  ) => {
    const formData = new FormData()
    formData.append('file', file)

    const config: AxiosRequestConfig = {
      params: { path, allow_overwrite: allowOverwrite },
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 1800000 // 30 minutes timeout for uploads
    }

    if (options?.onUploadProgress) {
      config.onUploadProgress = (progressEvent: any) => {
        const progress = Math.round((progressEvent.loaded * 100) / progressEvent.total)
        const uploadProgressEvent: UploadProgressEvent = {
          loaded: progressEvent.loaded,
          total: progressEvent.total,
          progress: progress,
          bytes: progressEvent.loaded,
          bytesPerSecond: progressEvent.bytesPerSecond || 0,
          estimatedRemaining: progressEvent.estimatedRemaining || 0
        }
        options.onUploadProgress!(uploadProgressEvent)
      }
    }

    if (options?.signal) {
      config.signal = options.signal
    }

    return api.post('/archive/upload', formData, config).then((res: any) => res.data)
  },

  // Create file or directory
  createArchiveItem: (request: CreateArchiveFileRequest) =>
    api.post('/archive/create', request).then((res: any) => res.data),

  // Delete file or directory
  deleteArchiveItem: (path: string) =>
    api.delete('/archive', { params: { path } }).then((res: any) => res.data),

  // Rename file or directory
  renameArchiveItem: (request: RenameArchiveFileRequest) =>
    api.post('/archive/rename', request).then((res: any) => res.data),

  // Calculate SHA256 hash
  calculateSHA256: (path: string): Promise<{ sha256: string }> =>
    api.get('/archive/sha256', { params: { path } }).then((res: any) => res.data),

  // Create archive from server files
  createArchive: (request: CreateArchiveRequest): Promise<CreateArchiveResponse> =>
    api.post('/archive/compress', request).then((res: any) => res.data),
}