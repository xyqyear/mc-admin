import { waitForTaskResult } from '@/features/tasks/commands';
import { getErrorMessage, type ApiError } from '@/shared/http/api'
import type { CreateFileRequest, RenameFileRequest, FileBatchDeleteResult } from "@/features/files/contracts";
import type { BackgroundTask } from '@/features/tasks/contracts';
import { taskQueryKeys } from "@/features/tasks/queries";
import { queryKeys } from "@/shared/http/api";
import { useMutation, useQueryClient, type QueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { fileApi } from "@/features/files/api";
import type {
  FileSearchRequest
} from "@/features/files/contracts";
import { useDownloadManager } from "@/features/tasks/downloads";
function invalidateFileList(queryClient: QueryClient, serverId: string | undefined) {
  queryClient.invalidateQueries({ queryKey: queryKeys.files.lists(serverId || "") });
}

export const useUpdateFile = (serverId: string | undefined) => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ path, content }: { path: string; content: string }) =>
      fileApi.updateFileContent(serverId!, path, content),
    onSuccess: () => {
      toast.success("文件更新成功");
      invalidateFileList(queryClient, serverId);
    },
    onError: (error: ApiError) => {
      toast.error(getErrorMessage(error, "更新文件失败"));
    },
  });
};

export const useCreateFile = (serverId: string | undefined) => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (createRequest: CreateFileRequest) =>
      fileApi.createFileOrDirectory(serverId!, createRequest),
    onSuccess: (_, variables) => {
      toast.success(
        `${variables.type === "file" ? "文件" : "文件夹"}创建成功`
      );
      invalidateFileList(queryClient, serverId);
    },
    onError: (error: ApiError) => {
      toast.error(getErrorMessage(error, "创建失败"));
    },
  });
};

export const useDeleteFile = (serverId: string | undefined) => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (path: string) =>
      waitForTaskResult(queryClient, await fileApi.deleteFileOrDirectory(serverId!, path)),
    onSuccess: () => {
      toast.success("删除成功");
      invalidateFileList(queryClient, serverId);
    },
    onError: (error: ApiError) => {
      toast.error(getErrorMessage(error, "删除失败"));
    },
  });
};

export const useBulkDeleteFiles = (serverId: string | undefined) => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (paths: string[]) => {
      const accepted = await fileApi.deleteFiles(serverId!, [...paths]);
      try {
        return await waitForTaskResult<FileBatchDeleteResult>(queryClient, accepted);
      } catch (error) {
        const task = queryClient.getQueryData<BackgroundTask>(taskQueryKeys.detail(accepted.task_id));
        if ((task?.status === 'failed' || task?.status === 'cancelled') && task.result && Array.isArray(task.result.results)) return task.result as unknown as FileBatchDeleteResult;
        throw error;
      }
    },
    onSuccess: (result) => {
      if (result.failed === 0 && result.pending === 0) {
        toast.success(`成功删除 ${result.deleted} 个条目`);
      } else {
        toast.warning(`删除结果：成功 ${result.deleted} 个，失败 ${result.failed} 个，未执行 ${result.pending} 个`);
      }
    },
    onError: (error: ApiError) => {
      toast.error(getErrorMessage(error, "批量删除失败"));
    },
  });
};

export const useRenameFile = (serverId: string | undefined) => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (renameRequest: RenameFileRequest) =>
      fileApi.renameFileOrDirectory(serverId!, renameRequest),
    onSuccess: () => {
      toast.success("重命名成功");
      invalidateFileList(queryClient, serverId);
    },
    onError: (error: ApiError) => {
      toast.error(getErrorMessage(error, "重命名失败"));
    },
  });
};

export const useRestoreFileOwnership = (serverId: string | undefined) => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => fileApi.restoreFileOwnership(serverId!),
    onSuccess: () => {
      toast.success("已开始修复文件所有权");
      queryClient.invalidateQueries({ queryKey: taskQueryKeys.all });
      queryClient.invalidateQueries({ queryKey: queryKeys.operations.all });
    },
    onError: (error: ApiError) => {
      toast.error(error.message || "修复文件所有权失败");
    },
  });
};

export const useSearchFiles = (serverId: string | undefined) => {
  return useMutation({
    mutationFn: ({ path = "/", searchRequest }: { path?: string; searchRequest: FileSearchRequest }) =>
      fileApi.searchFiles(serverId!, path, searchRequest),
    onError: (error: ApiError) => {
      toast.error(getErrorMessage(error, "搜索失败"));
    },
  });
};

export function useFileDownload(serverId: string | undefined) {
  const { executeDownload } = useDownloadManager();
  const downloadFile = async (path: string, filename: string) => {
    if (!serverId) return;
    await executeDownload(
      (onProgress, signal) => fileApi.downloadFileWithProgress(serverId, path, onProgress, signal),
      { filename, serverId }
    );
  };
  return { downloadFile };
}
