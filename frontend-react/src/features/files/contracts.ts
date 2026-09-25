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

export interface FileSearchRequest {
  regex: string;
  ignore_case?: boolean;
  search_subfolders?: boolean;
  min_size?: number;
  max_size?: number;
  newer_than?: string;
  older_than?: string;
}

export interface SearchFileItem {
  name: string;
  path: string;
  type: "file" | "directory";
  size: number;
  modified_at: string;
}

export interface FileSearchResponse {
  query: FileSearchRequest;
  results: SearchFileItem[];
  total_count: number;
  search_path: string;
}

export interface FileStructureItem {
  path: string;
  name: string;
  type: "file" | "directory";
  size?: number;
}

export interface MultiFileUploadRequest {
  files: FileStructureItem[];
}

export interface OverwriteConflict {
  path: string;
  type: "file" | "directory";
  current_size?: number;
  new_size?: number;
}

export interface UploadConflictResponse {
  session_id: string;
  conflicts: OverwriteConflict[];
}

export interface OverwriteDecision {
  path: string;
  overwrite: boolean;
}

export interface OverwritePolicy {
  mode: "always_overwrite" | "never_overwrite" | "per_file";
  decisions?: OverwriteDecision[];
}

export interface UploadFileResult {
  status: "success" | "failed" | "skipped";
  // For failed: error message. For skipped: "exists" or "no_decision".
  reason?: string;
}

export interface MultiFileUploadResult {
  message: string;
  results: Record<string, UploadFileResult>;
}
