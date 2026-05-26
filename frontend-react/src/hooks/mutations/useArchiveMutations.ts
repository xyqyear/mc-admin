import { archiveApi, type CreateArchiveFileRequest, type CreateArchiveRequest, type RenameArchiveFileRequest } from '@/hooks/api/archiveApi'
import { taskQueryKeys } from '@/hooks/queries/base/useTaskQueries'
import { queryKeys } from '@/utils/api'
import { useDownloadManager } from '@/utils/downloadUtils'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'

export const useArchiveMutations = () => {
  const queryClient = useQueryClient()
  const { executeDownload } = useDownloadManager()

  const getParentPath = (path: string) => {
    if (!path || path === '/') return '/'
    const normalized = path.endsWith('/') ? path.slice(0, -1) : path
    const lastSlashIndex = normalized.lastIndexOf('/')
    if (lastSlashIndex <= 0) return '/'
    return normalized.slice(0, lastSlashIndex)
  }

  const useCreateItem = () => {
    return useMutation({
      mutationFn: (request: CreateArchiveFileRequest) =>
        archiveApi.createArchiveItem(request),
      onSuccess: (_, request) => {
        queryClient.invalidateQueries({ queryKey: queryKeys.archive.files(request.path) })
        toast.success(`${request.type === 'file' ? '文件' : '目录'}创建成功`)
      },
      onError: (error: any) => {
        toast.error(`创建失败: ${error.message}`)
      }
    })
  }

  const useDeleteItem = () => {
    return useMutation({
      mutationFn: (path: string) => archiveApi.deleteArchiveItem(path),
      onSuccess: (_, path) => {
        queryClient.invalidateQueries({ queryKey: queryKeys.archive.files(getParentPath(path)) })
        toast.success('删除成功')
      },
      onError: (error: any) => {
        toast.error(`删除失败: ${error.message}`)
      }
    })
  }

  const useRenameItem = () => {
    return useMutation({
      mutationFn: (request: RenameArchiveFileRequest) =>
        archiveApi.renameArchiveItem(request),
      onSuccess: (_, request) => {
        queryClient.invalidateQueries({
          queryKey: queryKeys.archive.files(getParentPath(request.old_path))
        })
        toast.success('重命名成功')
      },
      onError: (error: any) => {
        toast.error(`重命名失败: ${error.message}`)
      }
    })
  }

  const downloadFile = async (path: string, filename: string) => {
    await executeDownload(
      (onProgress, signal) => archiveApi.downloadArchiveFileWithProgress(path, onProgress, signal),
      {
        filename,
      }
    );
  }

  const useCreateArchive = () => {
    return useMutation({
      mutationFn: (request: CreateArchiveRequest) =>
        archiveApi.createArchive(request),
      onSuccess: () => {
        // Archive list invalidation is deferred until the task completes
        // (handled in ServerFiles.tsx via the task completion callback).
        queryClient.invalidateQueries({ queryKey: taskQueryKeys.all })
      },
      onError: (error: any) => {
        toast.error(`创建压缩包失败: ${error.message}`)
      }
    })
  }


  return {
    useCreateItem,
    useDeleteItem,
    useRenameItem,
    useCreateArchive,
    downloadFile,
  }
}
