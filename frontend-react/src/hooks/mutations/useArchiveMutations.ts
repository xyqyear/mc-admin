import { useMutation, useQueryClient } from '@tanstack/react-query'
import { App } from 'antd'
import { archiveApi, type CreateArchiveFileRequest, type RenameArchiveFileRequest, type UploadOptions, type CreateArchiveRequest } from '@/hooks/api/archiveApi'
import { queryKeys } from '@/utils/api'
import { useDownloadManager } from '@/utils/downloadUtils'

export const useArchiveMutations = () => {
  const { message } = App.useApp()
  const queryClient = useQueryClient()
  const { executeDownload } = useDownloadManager()

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
        // Invalidate the root path files list
        queryClient.invalidateQueries({ queryKey: queryKeys.archive.files('/') })
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
        // Invalidate the root path files list
        queryClient.invalidateQueries({ queryKey: queryKeys.archive.files('/') })
        // Invalidate SHA256 cache for the old path
        queryClient.invalidateQueries({ queryKey: queryKeys.archive.sha256(request.old_path) })
        message.success('重命名成功')
      },
      onError: (error: any) => {
        message.error(`重命名失败: ${error.message}`)
      }
    })
  }

  // Update file content
  const useUpdateFileContent = () => {
    return useMutation({
      mutationFn: ({ path, content }: { path: string; content: string }) =>
        archiveApi.updateArchiveFileContent(path, content),
      onSuccess: (_, { path }) => {
        queryClient.invalidateQueries({ queryKey: queryKeys.archive.content(path) })
        // Invalidate SHA256 cache for the updated file
        queryClient.invalidateQueries({ queryKey: queryKeys.archive.sha256(path) })
        message.success('文件更新成功')
      },
      onError: (error: any) => {
        message.error(`更新失败: ${error.message}`)
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
      onSuccess: (data) => {
        // Invalidate archive file list to show the new archive
        queryClient.invalidateQueries({ queryKey: queryKeys.archive.files('/') })
        message.success(data.message)
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
    useUpdateFileContent,
    useCreateArchive,
    downloadFile,
  }
}