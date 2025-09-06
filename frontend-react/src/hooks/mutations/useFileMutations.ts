import type { CreateFileRequest, RenameFileRequest } from "@/types/Server";
import { queryKeys } from "@/utils/api";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { App } from "antd";
import { fileApi } from "../api/fileApi";

export const useFileMutations = (serverId: string | undefined) => {
  const queryClient = useQueryClient();
  const { message } = App.useApp();

  const invalidateFileList = () => {
    // Invalidate all file-related queries for this server
    queryClient.invalidateQueries({
      queryKey: [...queryKeys.files.all, serverId || ""],
    });
  };

  // 更新文件内容
  const useUpdateFile = () => {
    return useMutation({
      mutationFn: ({ path, content }: { path: string; content: string }) =>
        fileApi.updateFileContent(serverId!, path, content),
      onSuccess: (_, variables) => {
        message.success("文件更新成功");
        // Invalidate file content cache
        queryClient.invalidateQueries({
          queryKey: [...queryKeys.files.content(serverId || "", variables.path)],
        });
      },
      onError: (error: any) => {
        message.error(error.response?.data?.detail || "更新文件失败");
      },
    });
  };

  // 上传文件
  const useUploadFile = () => {
    return useMutation({
      mutationFn: ({ path, file }: { path: string; file: File }) =>
        fileApi.uploadFile(serverId!, path, file),
      onSuccess: () => {
        message.success("文件上传成功");
        invalidateFileList();
      },
      onError: (error: any) => {
        message.error(error.response?.data?.detail || "上传文件失败");
      },
    });
  };

  // 创建文件或目录
  const useCreateFile = () => {
    return useMutation({
      mutationFn: (createRequest: CreateFileRequest) =>
        fileApi.createFileOrDirectory(serverId!, createRequest),
      onSuccess: (_, variables) => {
        message.success(
          `${variables.type === "file" ? "文件" : "文件夹"}创建成功`
        );
        invalidateFileList();
      },
      onError: (error: any) => {
        message.error(error.response?.data?.detail || "创建失败");
      },
    });
  };

  // 删除文件或目录
  const useDeleteFile = () => {
    return useMutation({
      mutationFn: (path: string) =>
        fileApi.deleteFileOrDirectory(serverId!, path),
      onSuccess: () => {
        message.success("删除成功");
        invalidateFileList();
      },
      onError: (error: any) => {
        message.error(error.response?.data?.detail || "删除失败");
      },
    });
  };

  // 重命名文件或目录
  const useRenameFile = () => {
    return useMutation({
      mutationFn: (renameRequest: RenameFileRequest) =>
        fileApi.renameFileOrDirectory(serverId!, renameRequest),
      onSuccess: () => {
        message.success("重命名成功");
        invalidateFileList();
      },
      onError: (error: any) => {
        message.error(error.response?.data?.detail || "重命名失败");
      },
    });
  };

  // 下载文件 (非mutations，但是文件操作相关)
  const downloadFile = async (path: string, filename: string) => {
    try {
      const blob = await fileApi.downloadFile(serverId!, path);
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);
      message.success("下载开始");
    } catch (error: any) {
      message.error(error.response?.data?.detail || "下载失败");
    }
  };

  return {
    useUpdateFile,
    useUploadFile,
    useCreateFile,
    useDeleteFile,
    useRenameFile,
    downloadFile,
  };
};