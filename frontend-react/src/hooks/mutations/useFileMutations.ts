import type { CreateFileRequest, RenameFileRequest } from "@/types/Server";
import { queryKeys } from "@/utils/api";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { App } from "antd";
import { fileApi } from "@/hooks/api/fileApi";
import type {
  MultiFileUploadRequest,
  OverwritePolicy,
  MultiFileUploadResult,
  FileSearchRequest
} from "@/hooks/api/fileApi";
import { useDownloadManager } from "@/utils/downloadUtils";

export const useFileMutations = (serverId: string | undefined) => {
  const queryClient = useQueryClient();
  const { message } = App.useApp();
  const { executeDownload } = useDownloadManager();

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
      onSuccess: () => {
        message.success("文件更新成功");
        // Invalidate all file caches for this server, including list and content.
        invalidateFileList();
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

  // 批量删除文件或目录
  const useBulkDeleteFiles = () => {
    return useMutation({
      mutationFn: async (paths: string[]) => {
        const results = await Promise.allSettled(
          paths.map(path => fileApi.deleteFileOrDirectory(serverId!, path))
        );

        const successful = results.filter(result => result.status === 'fulfilled').length;
        const failed = results.filter(result => result.status === 'rejected').length;

        return { successful, failed, total: paths.length };
      },
      onSuccess: (result) => {
        if (result.failed === 0) {
          message.success(`成功删除 ${result.successful} 个文件`);
        } else {
          message.warning(`删除完成：成功 ${result.successful} 个，失败 ${result.failed} 个`);
        }
        invalidateFileList();
      },
      onError: (error: any) => {
        message.error(error.response?.data?.detail || "批量删除失败");
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

  // 多文件上传: 检查冲突
  const useCheckUploadConflicts = () => {
    return useMutation({
      mutationFn: ({ path, uploadRequest }: { path: string; uploadRequest: MultiFileUploadRequest }) =>
        fileApi.checkUploadConflicts(serverId!, path, uploadRequest),
      onError: (error: any) => {
        message.error(error.response?.data?.detail || "检查冲突失败");
      },
    });
  };

  // 多文件上传: 设置覆盖策略
  const useSetUploadPolicy = () => {
    return useMutation({
      mutationFn: ({ sessionId, policy, reusable }: { sessionId: string; policy: OverwritePolicy; reusable?: boolean }) =>
        fileApi.setUploadPolicy(serverId!, sessionId, policy, reusable),
      onError: (error: any) => {
        message.error(error.response?.data?.detail || "设置覆盖策略失败");
      },
    });
  };

  // 多文件上传: 执行上传
  const useUploadMultipleFiles = () => {
    return useMutation({
      mutationFn: ({
        sessionId,
        path,
        files,
        onProgress,
        abortSignal
      }: {
        sessionId: string;
        path: string;
        files: File[];
        onProgress?: (progress: { loaded: number; total: number; percent: number }) => void;
        abortSignal?: AbortSignal;
      }) =>
        fileApi.uploadMultipleFiles(serverId!, sessionId, path, files, onProgress, abortSignal),
      onSuccess: (result: MultiFileUploadResult) => {
        const successCount = Object.values(result.results).filter(r =>
          r.status === 'success'
        ).length;
        const totalCount = Object.keys(result.results).length;
        message.success(`上传完成！成功: ${successCount}/${totalCount}`);
        invalidateFileList();
      },
      onError: (error: any) => {
        message.error(error.response?.data?.detail || "上传失败");
      },
    });
  };

  // 下载文件 (非mutations，但是文件操作相关)
  const downloadFile = async (path: string, filename: string) => {
    if (!serverId) return;

    await executeDownload(
      (onProgress, signal) => fileApi.downloadFileWithProgress(serverId, path, onProgress, signal),
      {
        filename,
        serverId,
      }
    );
  };

  // 搜索文件
  const useSearchFiles = () => {
    return useMutation({
      mutationFn: ({ path = "/", searchRequest }: { path?: string; searchRequest: FileSearchRequest }) =>
        fileApi.searchFiles(serverId!, path, searchRequest),
      onError: (error: any) => {
        message.error(error.response?.data?.detail || "搜索失败");
      },
    });
  };

  return {
    useUpdateFile,
    useUploadFile,
    useCreateFile,
    useDeleteFile,
    useBulkDeleteFiles,
    useRenameFile,
    useCheckUploadConflicts,
    useSetUploadPolicy,
    useUploadMultipleFiles,
    useSearchFiles,
    downloadFile,
  };
};
