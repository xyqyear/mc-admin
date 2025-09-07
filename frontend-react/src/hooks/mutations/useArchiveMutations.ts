import { useMutation, useQueryClient } from '@tanstack/react-query'
import { App } from 'antd'
import { archiveApi, type CreateArchiveFileRequest, type RenameArchiveFileRequest, type UploadOptions } from '@/hooks/api/archiveApi'
import { queryKeys } from '@/utils/api'

export const useArchiveMutations = () => {
  const { message } = App.useApp()
  const queryClient = useQueryClient()

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
      onSuccess: (_, { path }) => {
        queryClient.invalidateQueries({ queryKey: queryKeys.archive.files(path) })
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
      onSuccess: () => {
        // Invalidate the root path files list
        queryClient.invalidateQueries({ queryKey: queryKeys.archive.files('/') })
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
      onSuccess: () => {
        // Invalidate the root path files list
        queryClient.invalidateQueries({ queryKey: queryKeys.archive.files('/') })
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
        message.success('文件更新成功')
      },
      onError: (error: any) => {
        message.error(`更新失败: ${error.message}`)
      }
    })
  }

  // Download file helper
  const downloadFile = async (path: string, filename: string) => {
    try {
      const blob = await archiveApi.downloadArchiveFile(path)
      const url = window.URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = filename
      document.body.appendChild(link)
      link.click()
      link.remove()
      window.URL.revokeObjectURL(url)
      message.success('下载开始')
    } catch (error: any) {
      message.error(`下载失败: ${error.message}`)
    }
  }

  return {
    useUploadFile,
    useCreateItem,
    useDeleteItem,
    useRenameItem,
    useUpdateFileContent,
    downloadFile,
  }
}