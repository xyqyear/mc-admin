import type { CreateFileRequest, RenameFileRequest } from "@/types/Server";
import { taskQueryKeys } from "@/hooks/queries/base/useTaskQueries";
import { queryKeys } from "@/utils/api";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { fileApi } from "@/hooks/api/fileApi";
import type {
  FileSearchRequest
} from "@/hooks/api/fileApi";
import { useDownloadManager } from "@/utils/downloadUtils";

export const useFileMutations = (serverId: string | undefined) => {
  const queryClient = useQueryClient();
  const { executeDownload } = useDownloadManager();

  const invalidateFileList = () => {
    queryClient.invalidateQueries({
      queryKey: queryKeys.files.lists(serverId || ""),
    });
  };

  const useUpdateFile = () => {
    return useMutation({
      mutationFn: ({ path, content }: { path: string; content: string }) =>
        fileApi.updateFileContent(serverId!, path, content),
      onSuccess: () => {
        toast.success("文件更新成功");
        invalidateFileList();
      },
      onError: (error: any) => {
        toast.error(error.response?.data?.detail || "更新文件失败");
      },
    });
  };

  const useCreateFile = () => {
    return useMutation({
      mutationFn: (createRequest: CreateFileRequest) =>
        fileApi.createFileOrDirectory(serverId!, createRequest),
      onSuccess: (_, variables) => {
        toast.success(
          `${variables.type === "file" ? "文件" : "文件夹"}创建成功`
        );
        invalidateFileList();
      },
      onError: (error: any) => {
        toast.error(error.response?.data?.detail || "创建失败");
      },
    });
  };

  const useDeleteFile = () => {
    return useMutation({
      mutationFn: (path: string) =>
        fileApi.deleteFileOrDirectory(serverId!, path),
      onSuccess: () => {
        toast.success("删除成功");
        invalidateFileList();
      },
      onError: (error: any) => {
        toast.error(error.response?.data?.detail || "删除失败");
      },
    });
  };

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
          toast.success(`成功删除 ${result.successful} 个文件`);
        } else {
          toast.warning(`删除完成：成功 ${result.successful} 个，失败 ${result.failed} 个`);
        }
        invalidateFileList();
      },
      onError: (error: any) => {
        toast.error(error.response?.data?.detail || "批量删除失败");
      },
    });
  };

  const useRenameFile = () => {
    return useMutation({
      mutationFn: (renameRequest: RenameFileRequest) =>
        fileApi.renameFileOrDirectory(serverId!, renameRequest),
      onSuccess: () => {
        toast.success("重命名成功");
        invalidateFileList();
      },
      onError: (error: any) => {
        toast.error(error.response?.data?.detail || "重命名失败");
      },
    });
  };

  const useRestoreFileOwnership = () => {
    return useMutation({
      mutationFn: () => fileApi.restoreFileOwnership(serverId!),
      onSuccess: () => {
        toast.success("已开始修复文件所有权");
        queryClient.invalidateQueries({ queryKey: taskQueryKeys.all });
      },
      onError: (error: any) => {
        toast.error(error.message || "修复文件所有权失败");
      },
    });
  };

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

  const useSearchFiles = () => {
    return useMutation({
      mutationFn: ({ path = "/", searchRequest }: { path?: string; searchRequest: FileSearchRequest }) =>
        fileApi.searchFiles(serverId!, path, searchRequest),
      onError: (error: any) => {
        toast.error(error.response?.data?.detail || "搜索失败");
      },
    });
  };

  return {
    useUpdateFile,
    useCreateFile,
    useDeleteFile,
    useBulkDeleteFiles,
    useRenameFile,
    useRestoreFileOwnership,
    useSearchFiles,
    downloadFile,
  };
};
