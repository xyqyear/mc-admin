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
    path: string = "/",
  ): Promise<FileListResponse> => {
    const response = await api.get(`/servers/${serverId}/files`, {
      params: { path },
    });
    return response.data;
  },

  // Get file content
  getFileContent: async (
    serverId: string,
    path: string,
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
    content: string,
  ): Promise<{ message: string }> => {
    const response = await api.post(
      `/servers/${serverId}/files/content`,
      { content },
      { params: { path } },
    );
    return response.data;
  },

  // Download file
  downloadFile: async (serverId: string, path: string): Promise<Blob> => {
    const response = await api.get(`/servers/${serverId}/files/download`, {
      params: { path },
      responseType: "blob",
    });
    return response.data;
  },

  // Upload file
  uploadFile: async (
    serverId: string,
    path: string,
    file: File,
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
      },
    );
    return response.data;
  },

  // Create file or directory
  createFileOrDirectory: async (
    serverId: string,
    createRequest: CreateFileRequest,
  ): Promise<{ message: string }> => {
    const response = await api.post(
      `/servers/${serverId}/files/create`,
      createRequest,
    );
    return response.data;
  },

  // Delete file or directory
  deleteFileOrDirectory: async (
    serverId: string,
    path: string,
  ): Promise<{ message: string }> => {
    const response = await api.delete(`/servers/${serverId}/files`, {
      params: { path },
    });
    return response.data;
  },

  // Rename file or directory
  renameFileOrDirectory: async (
    serverId: string,
    renameRequest: RenameFileRequest,
  ): Promise<{ message: string }> => {
    const response = await api.post(
      `/servers/${serverId}/files/rename`,
      renameRequest,
    );
    return response.data;
  },
};
