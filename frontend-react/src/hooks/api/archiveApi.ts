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

export interface CreateArchiveFileRequest {
  name: string
  type: 'file' | 'directory'
  path: string
}

export interface RenameArchiveFileRequest {
  old_path: string
  new_name: string
}

export interface CreateArchiveRequest {
  server_id: string
  path?: string | null
}

export interface CreateArchiveResponse {
  task_id: string
}

export interface InitArchiveUploadRequest {
  path: string
  filename: string
  size: number
  allow_overwrite?: boolean
}

export interface InitArchiveUploadResponse {
  upload_id: string
  offset: number
  chunk_size: number
  expires_at: number
}

export interface ArchiveUploadStatus {
  offset: number
  total: number
  chunkSize: number
  expiresAt: number
  filename: string
}

export interface ArchiveUploadChunkResponse {
  upload_id: string
  offset: number
  complete: boolean
  pending_verification?: boolean
  path?: string | null
  filename?: string | null
}

export interface VerifyArchiveUploadRequest {
  sha256: string
}

export interface VerifyArchiveUploadResponse {
  upload_id: string
  path: string
  filename: string
  sha256: string
}

export interface ArchiveSHA256Event {
  event_type: 'start' | 'progress' | 'complete' | 'error'
  loaded?: number
  total?: number
  percent?: number
  sha256?: string
  filename?: string
  message?: string
}

const parseHeaderNumber = (value: string | undefined, fallback = 0) => {
  if (!value) return fallback
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : fallback
}

export const archiveApi = {
  getArchiveFiles: (path: string = '/'): Promise<ArchiveFileListResponse> =>
    api.get('/archive', { params: { path } }).then((res: any) => res.data),

  downloadArchiveFileWithProgress: async (
    path: string,
    onProgress?: (progress: { loaded: number; total: number; percent: number; speed?: number }) => void,
    signal?: AbortSignal
  ): Promise<Blob> => {
    const startTime = Date.now()

    const response = await api.get('/archive/download', {
      params: { path },
      responseType: 'blob',
      timeout: 3600000,
      signal,
      onDownloadProgress: (progressEvent) => {
        if (onProgress && progressEvent.total) {
          const percent = Math.round((progressEvent.loaded * 100) / progressEvent.total)

          const currentTime = Date.now()
          const elapsedTime = (currentTime - startTime) / 1000
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

  initArchiveUpload: (
    request: InitArchiveUploadRequest,
    signal?: AbortSignal,
  ): Promise<InitArchiveUploadResponse> =>
    api.post('/archive/upload/init', request, { signal }).then((res: any) => res.data),

  getArchiveUploadStatus: async (
    uploadId: string,
    signal?: AbortSignal,
  ): Promise<ArchiveUploadStatus> => {
    const response = await api.head(`/archive/upload/${uploadId}`, { signal })
    return {
      offset: parseHeaderNumber(response.headers['upload-offset']),
      total: parseHeaderNumber(response.headers['upload-length']),
      chunkSize: parseHeaderNumber(response.headers['upload-chunk-size'], 8 * 1024 * 1024),
      expiresAt: parseHeaderNumber(response.headers['upload-expires']),
      filename: response.headers['upload-filename'] ?? '',
    }
  },

  uploadArchiveChunk: (
    uploadId: string,
    offset: number,
    chunk: Blob,
    signal?: AbortSignal,
  ): Promise<ArchiveUploadChunkResponse> =>
    api.patch(`/archive/upload/${uploadId}`, chunk, {
      headers: {
        'Content-Type': 'application/octet-stream',
        'Upload-Offset': String(offset),
      },
      timeout: 1800000,
      signal,
    }).then((res: any) => res.data),

  cancelArchiveUpload: (uploadId: string): Promise<void> =>
    api.delete(`/archive/upload/${uploadId}`).then(() => undefined),

  verifyArchiveUpload: (
    uploadId: string,
    request: VerifyArchiveUploadRequest,
    signal?: AbortSignal,
  ): Promise<VerifyArchiveUploadResponse> =>
    api.post(`/archive/upload/${uploadId}/verify`, request, { signal }).then((res: any) => res.data),

  createArchiveItem: (request: CreateArchiveFileRequest) =>
    api.post('/archive/create', request).then((res: any) => res.data),

  deleteArchiveItem: (path: string) =>
    api.delete('/archive', { params: { path } }).then((res: any) => res.data),

  renameArchiveItem: (request: RenameArchiveFileRequest) =>
    api.post('/archive/rename', request).then((res: any) => res.data),

  createArchive: (request: CreateArchiveRequest): Promise<CreateArchiveResponse> =>
    api.post('/archive/compress', request).then((res: any) => res.data),
}
