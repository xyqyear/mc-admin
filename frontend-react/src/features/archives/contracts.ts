
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
