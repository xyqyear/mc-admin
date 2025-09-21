import type {
  CreateFileRequest,
  FileContent,
  FileListResponse,
  RenameFileRequest,
} from "@/types/Server";
import { api } from "@/utils/api";

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
};
