import { archiveApi, type CreateArchiveFileRequest, type CreateArchiveRequest, type RenameArchiveFileRequest, type UploadOptions } from '@/hooks/api/archiveApi'
import { taskQueryKeys } from '@/hooks/queries/base/useTaskQueries'
import { queryKeys } from '@/utils/api'
import { useDownloadManager } from '@/utils/downloadUtils'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { App } from 'antd'

export const useArchiveMutations = () => {
  const { message } = App.useApp()
  const queryClient = useQueryClient()
  const { executeDownload } = useDownloadManager()

  const getParentPath = (path: string) => {
    if (!path || path === '/') return '/'
    const normalized = path.endsWith('/') ? path.slice(0, -1) : path
    const lastSlashIndex = normalized.lastIndexOf('/')
    if (lastSlashIndex <= 0) return '/'
    return normalized.slice(0, lastSlashIndex)
  }

  // Upload file
  const useUploadFile = () => {
    return useMutation({
      mutationFn: ({
        path,
        file,
        allowOverwrite,
        options
      }: {
        path: string;
        file: File;
        allowOverwrite?: boolean;
        options?: UploadOptions;
      }) =>
        archiveApi.uploadArchiveFile(path, file, allowOverwrite, options),
      onSuccess: (_, { path, file }) => {
        queryClient.invalidateQueries({ queryKey: queryKeys.archive.files(path) })
        // Invalidate SHA256 cache for the uploaded file
        const filePath = path === '/' ? `/${file.name}` : `${path}/${file.name}`
        queryClient.invalidateQueries({ queryKey: queryKeys.archive.sha256(filePath) })
        message.success('文件上传成功')
      },
      onError: (error: any) => {
        message.error(`上传失败: ${error.message}`)
      }
    })
  }

  // Create file or directory
  const useCreateItem = () => {
    return useMutation({
      mutationFn: (request: CreateArchiveFileRequest) =>
        archiveApi.createArchiveItem(request),
      onSuccess: (_, request) => {
        queryClient.invalidateQueries({ queryKey: queryKeys.archive.files(request.path) })
        message.success(`${request.type === 'file' ? '文件' : '目录'}创建成功`)
      },
      onError: (error: any) => {
        message.error(`创建失败: ${error.message}`)
      }
    })
  }

  // Delete file or directory
  const useDeleteItem = () => {
    return useMutation({
      mutationFn: (path: string) => archiveApi.deleteArchiveItem(path),
      onSuccess: (_, path) => {
        // Invalidate the parent path files list
        queryClient.invalidateQueries({ queryKey: queryKeys.archive.files(getParentPath(path)) })
        // Invalidate SHA256 cache for the deleted file
        queryClient.invalidateQueries({ queryKey: queryKeys.archive.sha256(path) })
        message.success('删除成功')
      },
      onError: (error: any) => {
        message.error(`删除失败: ${error.message}`)
      }
    })
  }

  // Rename file or directory
  const useRenameItem = () => {
    return useMutation({
      mutationFn: (request: RenameArchiveFileRequest) =>
        archiveApi.renameArchiveItem(request),
      onSuccess: (_, request) => {
        // Invalidate the parent path files list
        queryClient.invalidateQueries({
          queryKey: queryKeys.archive.files(getParentPath(request.old_path))
        })
        // Invalidate SHA256 cache for the old path
        queryClient.invalidateQueries({ queryKey: queryKeys.archive.sha256(request.old_path) })
        message.success('重命名成功')
      },
      onError: (error: any) => {
        message.error(`重命名失败: ${error.message}`)
      }
    })
  }

  // Download file helper with progress tracking
  const downloadFile = async (path: string, filename: string) => {
    await executeDownload(
      (onProgress, signal) => archiveApi.downloadArchiveFileWithProgress(path, onProgress, signal),
      {
        filename,
      }
    );
  }

  // Create archive from server files
  const useCreateArchive = () => {
    return useMutation({
      mutationFn: (request: CreateArchiveRequest) =>
        archiveApi.createArchive(request),
      onSuccess: () => {
        // Invalidate task queries to show the new task immediately
        queryClient.invalidateQueries({ queryKey: taskQueryKeys.all })
        // Note: archive file list will be invalidated when task completes (in ServerFiles.tsx)
      },
      onError: (error: any) => {
        message.error(`创建压缩包失败: ${error.message}`)
      }
    })
  }


  return {
    useUploadFile,
    useCreateItem,
    useDeleteItem,
    useRenameItem,
    useCreateArchive,
    downloadFile,
  }
}
