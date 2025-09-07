import api from '@/utils/api'

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

  // Download file
  downloadArchiveFile: (path: string): Promise<Blob> =>
    api.get('/archive/download', { 
      params: { path },
      responseType: 'blob'
    }).then((res: any) => res.data),

  // Upload file
  uploadArchiveFile: (
    path: string,
    file: File,
    allowOverwrite: boolean = false,
    options?: UploadOptions
  ) => {
    const formData = new FormData()
    formData.append('file', file)
    
    const config: any = {
      params: { path, allow_overwrite: allowOverwrite },
      headers: { 'Content-Type': 'multipart/form-data' }
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
}