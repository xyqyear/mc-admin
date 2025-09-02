// 重新导出新的类型定义，保持向后兼容
export type { ServerInfo, ServerStatus, ServerType } from './ServerInfo'
export type { ServerFullInfo, ServerRuntime, SystemInfo } from './ServerRuntime'

// 保持现有的类型定义以兼容老代码
export interface Player {
  username: string
  uuid: string
  firstJoined?: string
  lastSeen?: string
  playtimeHours?: number
  isOnline: boolean
}

export interface Backup {
  id: string
  serverId: string
  name: string
  size: number
  createdAt: string
  type: 'manual' | 'auto' | 'pre-update'
  description?: string
}

export interface ServerLog {
  timestamp: string
  level: 'INFO' | 'WARN' | 'ERROR' | 'DEBUG'
  message: string
  source?: string
}

export interface FileItem {
  name: string
  path: string
  type: 'file' | 'directory'
  size: number
  modified_at: string
  is_editable: boolean
  is_config: boolean
}

export interface FileListResponse {
  items: FileItem[]
  current_path: string
}

export interface FileContent {
  content: string
}

export interface CreateFileRequest {
  name: string
  type: 'file' | 'directory'
  path: string
}

export interface RenameFileRequest {
  old_path: string
  new_name: string
}