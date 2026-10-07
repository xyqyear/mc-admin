import { waitForTaskResult } from '@/features/tasks/commands'
import type { ApiError } from '@/shared/http/api'
import { archiveApi } from '@/features/archives/api';
import type { CreateArchiveRequest, RenameArchiveFileRequest } from '@/features/archives/contracts';
import { taskQueryKeys } from '@/features/tasks/queries'
import { queryKeys } from '@/shared/http/api'
import { useDownloadManager } from '@/features/tasks/downloads'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { formatLocalFilenameTimestamp } from '@/shared/utils/formatUtils'
const getParentPath = (path: string) => {
  if (!path || path === '/') return '/'
  const normalized = path.endsWith('/') ? path.slice(0, -1) : path
  const lastSlashIndex = normalized.lastIndexOf('/')
  if (lastSlashIndex <= 0) return '/'
  return normalized.slice(0, lastSlashIndex)
}

export const useDeleteItem = () => {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (path: string) => waitForTaskResult(queryClient, await archiveApi.deleteArchiveItem(path)),
    onSuccess: (_, path) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.archive.files(getParentPath(path)) })
      toast.success('删除成功')
    },
    onError: (error: ApiError) => {
      toast.error(`删除失败: ${error.message}`)
    }
  })
}

export const useRenameItem = () => {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (request: RenameArchiveFileRequest) =>
      archiveApi.renameArchiveItem(request),
    onSettled: () => { void queryClient.invalidateQueries({ queryKey: queryKeys.operations.all }) },
    onSuccess: (_, request) => {
      queryClient.invalidateQueries({
        queryKey: queryKeys.archive.files(getParentPath(request.old_path))
      })
      toast.success('重命名成功')
    },
    onError: (error: ApiError) => {
      toast.error(`重命名失败: ${error.message}`)
    }
  })
}

export const useCreateArchive = () => {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (request: CreateArchiveRequest) =>
      archiveApi.createArchive({ ...request, client_timestamp: request.client_timestamp ?? formatLocalFilenameTimestamp() }),
    onSettled: () => { void queryClient.invalidateQueries({ queryKey: queryKeys.operations.all }) },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: taskQueryKeys.all })
    },
    onError: (error: ApiError) => {
      toast.error(`创建压缩包失败: ${error.message}`)
    }
  })
}

export function useArchiveDownload() {
  const { executeDownload } = useDownloadManager();
  const downloadFile = async (path: string, filename: string) => {
    await executeDownload(
      (onProgress, signal) => archiveApi.downloadArchiveFileWithProgress(path, onProgress, signal),
      { filename },
    );
  }
  return { downloadFile };
}
