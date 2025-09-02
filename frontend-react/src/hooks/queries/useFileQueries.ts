import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { App } from 'antd'
import { fileApi } from '../api/fileApi'
import { queryKeys } from '@/utils/api'
import type { CreateFileRequest, RenameFileRequest } from '@/types/Server'

export const useFileList = (serverId: string | undefined, path: string = "/") => {
  return useQuery({
    queryKey: [...queryKeys.files.list(serverId || "", path)],
    queryFn: () => fileApi.listFiles(serverId!, path),
    enabled: !!serverId,
    staleTime: 1000 * 30, // 30 seconds
    refetchOnWindowFocus: true,
  })
}

export const useFileContent = (serverId: string | undefined, path: string | null) => {
  return useQuery({
    queryKey: [...queryKeys.files.content(serverId || "", path || "")],
    queryFn: () => fileApi.getFileContent(serverId!, path!),
    enabled: !!serverId && !!path,
    staleTime: 1000 * 60, // 1 minute
  })
}

export const useFileOperations = (serverId: string | undefined) => {
  const queryClient = useQueryClient()
  const { message } = App.useApp()

  const invalidateFileList = () => {
    queryClient.invalidateQueries({
      queryKey: queryKeys.files.lists(serverId || "")
    })
  }

  const updateFileMutation = useMutation({
    mutationFn: ({ path, content }: { path: string, content: string }) =>
      fileApi.updateFileContent(serverId!, path, content),
    onSuccess: (_, variables) => {
      message.success('文件更新成功')
      // Invalidate file content cache
      queryClient.invalidateQueries({
        queryKey: [...queryKeys.files.content(serverId || "", variables.path)]
      })
    },
    onError: (error: any) => {
      message.error(error.response?.data?.detail || '更新文件失败')
    }
  })

  const uploadFileMutation = useMutation({
    mutationFn: ({ path, file }: { path: string, file: File }) =>
      fileApi.uploadFile(serverId!, path, file),
    onSuccess: () => {
      message.success('文件上传成功')
      invalidateFileList()
    },
    onError: (error: any) => {
      message.error(error.response?.data?.detail || '上传文件失败')
    }
  })

  const createFileMutation = useMutation({
    mutationFn: (createRequest: CreateFileRequest) => fileApi.createFileOrDirectory(serverId!, createRequest),
    onSuccess: (_, variables) => {
      message.success(`${variables.type === 'file' ? '文件' : '文件夹'}创建成功`)
      invalidateFileList()
    },
    onError: (error: any) => {
      message.error(error.response?.data?.detail || '创建失败')
    }
  })

  const deleteFileMutation = useMutation({
    mutationFn: (path: string) => fileApi.deleteFileOrDirectory(serverId!, path),
    onSuccess: () => {
      message.success('删除成功')
      invalidateFileList()
    },
    onError: (error: any) => {
      message.error(error.response?.data?.detail || '删除失败')
    }
  })

  const renameFileMutation = useMutation({
    mutationFn: (renameRequest: RenameFileRequest) => fileApi.renameFileOrDirectory(serverId!, renameRequest),
    onSuccess: () => {
      message.success('重命名成功')
      invalidateFileList()
    },
    onError: (error: any) => {
      message.error(error.response?.data?.detail || '重命名失败')
    }
  })

  const downloadFile = async (path: string, filename: string) => {
    try {
      const blob = await fileApi.downloadFile(serverId!, path)
      const url = window.URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = filename
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      window.URL.revokeObjectURL(url)
      message.success('下载开始')
    } catch (error: any) {
      message.error(error.response?.data?.detail || '下载失败')
    }
  }

  return {
    updateFile: updateFileMutation.mutate,
    uploadFile: uploadFileMutation.mutate,
    createFile: createFileMutation.mutate,
    deleteFile: deleteFileMutation.mutate,
    renameFile: renameFileMutation.mutate,
    downloadFile,
    isUpdating: updateFileMutation.isPending,
    isUploading: uploadFileMutation.isPending,
    isCreating: createFileMutation.isPending,
    isDeleting: deleteFileMutation.isPending,
    isRenaming: renameFileMutation.isPending,
  }
}