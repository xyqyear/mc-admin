export type { ServerInfo, ServerStatus, ServerType } from "@/types/ServerInfo";
export type {
  ServerFullInfo,
  ServerRuntime,
  SystemInfo
} from "@/types/ServerRuntime";

export interface Backup {
  id: string;
  serverId: string;
  name: string;
  size: number;
  createdAt: string;
  type: "manual" | "auto" | "pre-update";
  description?: string;
}

export interface ServerLog {
  timestamp: string;
  level: "INFO" | "WARN" | "ERROR" | "DEBUG";
  message: string;
  source?: string;
}

export interface FileItem {
  name: string;
  path: string;
  type: "file" | "directory";
  size: number;
  /** Unix epoch seconds. */
  modified_at: number;
}

export interface FileListResponse {
  items: FileItem[];
  current_path: string;
}

export interface FileContent {
  content: string;
}

export interface CreateFileRequest {
  name: string;
  type: "file" | "directory";
  path: string;
}

export interface RenameFileRequest {
  old_path: string;
  new_name: string;
}

export interface OwnershipRestoreTaskResponse {
  task_id: string;
}
