import type {
  CreateFileRequest,
  FileContent,
  FileListResponse,
  RenameFileRequest,
} from "@/types/Server";
import { api } from "@/utils/api";

// Multi-file upload types
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
  reason?: string; // Error message for failed, reason for skipped ("exists", "no_decision")
}

export interface MultiFileUploadResult {
  message: string;
  results: Record<string, UploadFileResult>; // Key is file path, value is result
}

export const fileApi = {
  // List files and directories
  listFiles: async (
    serverId: string,
    path: string = "/"
  ): Promise<FileListResponse> => {
    const response = await api.get(`/servers/${serverId}/files`, {
      params: { path },
    });
    return response.data;
  },

  // Get file content
  getFileContent: async (
    serverId: string,
    path: string
  ): Promise<FileContent> => {
    const response = await api.get(`/servers/${serverId}/files/content`, {
      params: { path },
    });
    return response.data;
  },

  // Update file content
  updateFileContent: async (
    serverId: string,
    path: string,
    content: string
  ): Promise<{ message: string }> => {
    const response = await api.post(
      `/servers/${serverId}/files/content`,
      { content },
      { params: { path } }
    );
    return response.data;
  },

  // Download file with progress tracking and cancellation support
  downloadFileWithProgress: async (
    serverId: string,
    path: string,
    onProgress?: (progress: { loaded: number; total: number; percent: number; speed?: number }) => void,
    signal?: AbortSignal
  ): Promise<Blob> => {
    const startTime = Date.now()

    const response = await api.get(`/servers/${serverId}/files/download`, {
      params: { path },
      responseType: "blob",
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
  uploadFile: async (
    serverId: string,
    path: string,
    file: File
  ): Promise<{ message: string }> => {
    const formData = new FormData();
    formData.append("file", file);

    const response = await api.post(
      `/servers/${serverId}/files/upload`,
      formData,
      {
        params: { path },
        headers: {
          "Content-Type": "multipart/form-data",
        },
        timeout: 1800000, // 30 minutes timeout for uploads
      }
    );
    return response.data;
  },

  // Create file or directory
  createFileOrDirectory: async (
    serverId: string,
    createRequest: CreateFileRequest
  ): Promise<{ message: string }> => {
    const response = await api.post(
      `/servers/${serverId}/files/create`,
      createRequest
    );
    return response.data;
  },

  // Delete file or directory
  deleteFileOrDirectory: async (
    serverId: string,
    path: string
  ): Promise<{ message: string }> => {
    const response = await api.delete(`/servers/${serverId}/files`, {
      params: { path },
    });
    return response.data;
  },

  // Rename file or directory
  renameFileOrDirectory: async (
    serverId: string,
    renameRequest: RenameFileRequest
  ): Promise<{ message: string }> => {
    const response = await api.post(
      `/servers/${serverId}/files/rename`,
      renameRequest
    );
    return response.data;
  },

  // Multi-file upload: Check for conflicts
  checkUploadConflicts: async (
    serverId: string,
    path: string,
    uploadRequest: MultiFileUploadRequest
  ): Promise<UploadConflictResponse> => {
    const response = await api.post(
      `/servers/${serverId}/files/upload/check`,
      uploadRequest,
      { params: { path } }
    );
    return response.data;
  },

  // Multi-file upload: Set overwrite policy
  setUploadPolicy: async (
    serverId: string,
    sessionId: string,
    policy: OverwritePolicy,
    reusable: boolean = false
  ): Promise<{ message: string }> => {
    const response = await api.post(
      `/servers/${serverId}/files/upload/policy`,
      policy,
      { params: { session_id: sessionId, reusable } }
    );
    return response.data;
  },

  // Multi-file upload: Upload multiple files with chunking for large file sets
  uploadMultipleFiles: async (
    serverId: string,
    sessionId: string,
    path: string,
    files: File[],
    onProgress?: (progress: { loaded: number; total: number; percent: number }) => void,
    abortSignal?: AbortSignal
  ): Promise<MultiFileUploadResult> => {
    const CHUNK_SIZE = 1000; // Maximum files per request
    const totalSize = files.reduce((sum, file) => sum + file.size, 0);
    let totalLoaded = 0;

    // Initialize combined results
    const combinedResults: MultiFileUploadResult = {
      message: "Files uploaded successfully",
      results: {}
    };

    // If files count is within limit, upload directly
    if (files.length <= CHUNK_SIZE) {
      const formData = new FormData();
      files.forEach(file => {
        formData.append("files", file);
      });

      const response = await api.post(
        `/servers/${serverId}/files/upload/multiple`,
        formData,
        {
          params: { session_id: sessionId, path },
          headers: {
            "Content-Type": "multipart/form-data",
          },
          timeout: 1800000, // 30 minutes timeout for uploads
          signal: abortSignal,
          onUploadProgress: (progressEvent) => {
            if (onProgress && progressEvent.total) {
              const percent = Math.round((progressEvent.loaded * 100) / progressEvent.total);
              onProgress({
                loaded: progressEvent.loaded,
                total: progressEvent.total,
                percent,
              });
            }
          },
        }
      );
      return response.data;
    }

    // Split files into chunks for large file sets
    const chunks: File[][] = [];
    for (let i = 0; i < files.length; i += CHUNK_SIZE) {
      chunks.push(files.slice(i, i + CHUNK_SIZE));
    }

    // Upload each chunk sequentially
    for (let chunkIndex = 0; chunkIndex < chunks.length; chunkIndex++) {
      const chunk = chunks[chunkIndex];
      const chunkSize = chunk.reduce((sum, file) => sum + file.size, 0);

      const formData = new FormData();
      chunk.forEach(file => {
        formData.append("files", file);
      });

      const chunkResponse = await api.post(
        `/servers/${serverId}/files/upload/multiple`,
        formData,
        {
          params: { session_id: sessionId, path },
          headers: {
            "Content-Type": "multipart/form-data",
          },
          timeout: 1800000, // 30 minutes timeout for uploads
          signal: abortSignal,
          onUploadProgress: (progressEvent) => {
            if (onProgress && progressEvent.total) {
              // 当前chunk的上传进度
              const chunkProgress = progressEvent.loaded / progressEvent.total;
              // 当前chunk在总体中的比例
              const chunkRatio = chunkSize / totalSize;
              // 之前chunks已完成的比例
              const previousProgress = totalLoaded / totalSize;
              // 全局进度 = 之前完成的 + 当前chunk进度 * 当前chunk占比
              const globalProgress = previousProgress + (chunkProgress * chunkRatio);
              const globalLoaded = Math.round(globalProgress * totalSize);
              const percent = Math.round(globalProgress * 100);

              onProgress({
                loaded: globalLoaded,
                total: totalSize,
                percent,
              });
            }
          },
        }
      );

      // Merge results from this chunk
      Object.assign(combinedResults.results, chunkResponse.data.results);

      // Update total loaded for next chunk
      totalLoaded += chunkSize;
    }

    return combinedResults;
  },
};
