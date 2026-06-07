import type {
  CreateFileRequest,
  FileContent,
  FileListResponse,
  OwnershipRestoreTaskResponse,
  RenameFileRequest,
} from "@/types/Server";
import { api } from "@/utils/api";

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

export const fileApi = {
  listFiles: async (
    serverId: string,
    path: string = "/"
  ): Promise<FileListResponse> => {
    const response = await api.get(`/servers/${serverId}/files`, {
      params: { path },
    });
    return response.data;
  },

  getFileContent: async (
    serverId: string,
    path: string
  ): Promise<FileContent> => {
    const response = await api.get(`/servers/${serverId}/files/content`, {
      params: { path },
    });
    return response.data;
  },

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

  deleteFileOrDirectory: async (
    serverId: string,
    path: string
  ): Promise<{ message: string }> => {
    const response = await api.delete(`/servers/${serverId}/files`, {
      params: { path },
    });
    return response.data;
  },

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

  restoreFileOwnership: async (
    serverId: string
  ): Promise<OwnershipRestoreTaskResponse> => {
    const response = await api.post(
      `/servers/${serverId}/files/ownership/restore`,
      {},
    );
    return response.data;
  },

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

  // Chunks files into batches when count exceeds the per-request limit;
  // progress is normalized across all chunks so the caller sees one curve.
  uploadMultipleFiles: async (
    serverId: string,
    sessionId: string,
    path: string,
    files: File[],
    onProgress?: (progress: { loaded: number; total: number; percent: number }) => void,
    abortSignal?: AbortSignal
  ): Promise<MultiFileUploadResult> => {
    const CHUNK_SIZE = 1000;
    const totalSize = files.reduce((sum, file) => sum + file.size, 0);
    let totalLoaded = 0;

    const combinedResults: MultiFileUploadResult = {
      message: "Files uploaded successfully",
      results: {}
    };

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
          timeout: 1800000,
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

    const chunks: File[][] = [];
    for (let i = 0; i < files.length; i += CHUNK_SIZE) {
      chunks.push(files.slice(i, i + CHUNK_SIZE));
    }

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
          timeout: 1800000,
          signal: abortSignal,
          onUploadProgress: (progressEvent) => {
            if (onProgress && progressEvent.total) {
              const chunkProgress = progressEvent.loaded / progressEvent.total;
              const chunkRatio = chunkSize / totalSize;
              const previousProgress = totalLoaded / totalSize;
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

      Object.assign(combinedResults.results, chunkResponse.data.results);

      totalLoaded += chunkSize;
    }

    return combinedResults;
  },

  searchFiles: async (
    serverId: string,
    path: string = "/",
    searchRequest: FileSearchRequest
  ): Promise<FileSearchResponse> => {
    const response = await api.post(
      `/servers/${serverId}/files/search`,
      searchRequest,
      { params: { path } }
    );
    return response.data;
  },
};
