import { useArchiveMutations } from '@/features/archives/commands'
import { useServerMutations } from '@/features/servers/commands'
import { useTaskQueries } from '@/features/tasks/queries'
import { useServerQueries } from '@/features/servers/queries'
import { useConfirm } from '@/shared/hooks/useConfirm'
import React, { useEffect, useState } from 'react'
import { toast } from 'sonner'
import { useFileMutations } from '@/features/files/commands'
import type { FileSearchBoxRef } from '@/features/files/components/FileSearchBox'
import type { FileItem } from '@/features/files/contracts'
import { useFileList } from '@/features/files/queries'
import { searchFiles } from '@/features/files/search'
import { useFileEditor } from '@/features/files/useFileEditor'
import { useFileNavigation } from '@/features/files/useFileNavigation'
import { usePageDragUpload } from '@/shared/hooks/usePageDragUpload'

export function useFileBrowser(id: string | undefined) {
  const { confirm, confirmDialog } = useConfirm()

  const { useServerInfo } = useServerQueries()
  const { data: serverInfo } = useServerInfo(id || "")
  const hasServerInfo = !!serverInfo

  const [selectedFiles, setSelectedFiles] = useState<string[]>([])
  const navigation = useFileNavigation(() => setSelectedFiles([]))
  const { currentPath, searchQuery, useRegex, inputSearchTerm, updatePath, handleSearchChange, handleSearch, handleRegexChange, handleSearchClear } = navigation
  const editor = useFileEditor(id)
  const { editingFile, isEditDialogOpen, isDiffDialogOpen, setIsDiffDialogOpen, fileContent, setFileContent, originalFileContent, isLoadingContent, contentError, refetchContent, editorDraft, updateFileMutation, getCurrentFileLanguageConfig, handleFileEdit, handleFileSave, handleShowDiff, closeEditor } = editor

  const { data: fileData, isLoading: isLoadingFiles, isFetching: isFetchingFiles, error: filesError, refetch } = useFileList(id, currentPath)

  const filteredFileData = React.useMemo(() => {
    if (!fileData?.items || !searchQuery.trim()) {
      return fileData
    }
    const filteredItems = searchFiles(fileData.items, searchQuery, useRegex)
    return { ...fileData, items: filteredItems }
  }, [fileData, searchQuery, useRegex])

  const {
    useCreateFile,
    useDeleteFile,
    useBulkDeleteFiles,
    useRenameFile,
    useRestoreFileOwnership,
    downloadFile
  } = useFileMutations(id)

  const createFileMutation = useCreateFile()
  const deleteFileMutation = useDeleteFile()
  const bulkDeleteMutation = useBulkDeleteFiles()
  const renameFileMutation = useRenameFile()
  const restoreOwnershipMutation = useRestoreFileOwnership()

  const { usePopulateServer } = useServerMutations()
  const populateServerMutation = usePopulateServer()

  const { useCreateArchive, downloadFile: downloadArchiveFile } = useArchiveMutations()
  const createArchiveMutation = useCreateArchive()

  const { useTask } = useTaskQueries()

  const [isCreateDialogOpen, setIsCreateDialogOpen] = useState(false)
  const [isMultiFileUploadDialogOpen, setIsMultiFileUploadDialogOpen] = useState(false)
  const [isRenameDialogOpen, setIsRenameDialogOpen] = useState(false)
  const [renamingFile, setRenamingFile] = useState<FileItem | null>(null)
  const [selectedUploadFiles, setSelectedUploadFiles] = useState<File[]>([])
  const [pageSize, setPageSize] = useState(20)
  const [currentPage, setCurrentPage] = useState(1)

  const [isArchiveDialogOpen, setIsArchiveDialogOpen] = useState(false)
  const [populateTaskId, setPopulateTaskId] = useState<string | null>(null)
  const [isPopulateProgressDialogOpen, setIsPopulateProgressDialogOpen] = useState(false)

  const [isCompressionConfirmDialogOpen, setIsCompressionConfirmDialogOpen] = useState(false)
  const [isCompressionResultDialogOpen, setIsCompressionResultDialogOpen] = useState(false)
  const [compressionFile, setCompressionFile] = useState<FileItem | null>(null)
  const [compressionType, setCompressionType] = useState<'file' | 'folder' | 'server'>('file')
  const [compressionResult, setCompressionResult] = useState<{ filename: string, message: string } | null>(null)
  const [compressionTaskId, setCompressionTaskId] = useState<string | null>(null)
  const [ownershipTaskId, setOwnershipTaskId] = useState<string | null>(null)

  const { data: compressionTask } = useTask(compressionTaskId || '')
  const { data: ownershipTask } = useTask(ownershipTaskId || '')

  const [isDeepSearchDialogOpen, setIsDeepSearchDialogOpen] = useState(false)
  const searchBoxRef = React.useRef<FileSearchBoxRef>(null)

  const { isDragging, isScanning } = usePageDragUpload({
    onFileDrop: (files) => {
      setSelectedUploadFiles(files)
      setIsMultiFileUploadDialogOpen(true)
      toast.info(`已选择 ${files.length} 个文件，请确认上传`)
    },
    onError: (errorMessage) => {
      toast.error(errorMessage)
    },
    allowDirectories: true
  })

  React.useEffect(() => {
    setCurrentPage(1)
  }, [currentPath])

  useEffect(() => {
    if (!compressionTask || !compressionTaskId) return

    if (compressionTask.status === 'completed' && compressionTask.result) {
      setCompressionResult({
        filename: compressionTask.result.filename as string,
        message: 'Compression complete'
      })
      setIsCompressionConfirmDialogOpen(false)
      setIsCompressionResultDialogOpen(true)
      setCompressionTaskId(null)
    } else if (compressionTask.status === 'failed') {
      toast.error(`压缩失败: ${compressionTask.error}`)
      setCompressionTaskId(null)
    } else if (compressionTask.status === 'cancelled') {
      toast.info('压缩任务已取消')
      setCompressionTaskId(null)
    }
  }, [compressionTask, compressionTaskId])

  useEffect(() => {
    if (!ownershipTask || !ownershipTaskId) return

    if (ownershipTask.status === 'completed') {
      const uid = ownershipTask.result?.uid
      const gid = ownershipTask.result?.gid
      const owner = typeof uid === 'number' && typeof gid === 'number'
        ? `为 ${uid}:${gid}`
        : ''
      toast.success(`文件所有权已修复${owner}`)
      setOwnershipTaskId(null)
    } else if (ownershipTask.status === 'failed') {
      toast.error(`修复文件所有权失败: ${ownershipTask.error || '未知错误'}`)
      setOwnershipTaskId(null)
    } else if (ownershipTask.status === 'cancelled') {
      toast.info('文件所有权修复已取消')
      setOwnershipTaskId(null)
    }
  }, [ownershipTask, ownershipTaskId])

  React.useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key === 'f') {
        event.preventDefault()
        searchBoxRef.current?.focus()
      }
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [])

  const handleFileDelete = (file: FileItem) => {
    if (id) deleteFileMutation.mutate(file.path)
  }

  const handleFileDownload = (file: FileItem) => {
    if (file.type === 'directory') {
      toast.info('请点击压缩按钮进行压缩下载')
      return
    }
    if (id) downloadFile(file.path, file.name)
  }

  const handleFileRename = (file: FileItem) => {
    setRenamingFile(file)
    setIsRenameDialogOpen(true)
  }

  const handleRenameSubmit = (newName: string) => {
    if (!renamingFile || !id) return
    renameFileMutation.mutate({
      old_path: renamingFile.path,
      new_name: newName
    })
    setIsRenameDialogOpen(false)
    setRenamingFile(null)
  }

  const handleFolderOpen = (folder: FileItem) => {
    if (folder.type === 'directory') updatePath(folder.path)
  }

  const handleNavigateToPath = (path: string) => updatePath(path)

  const handleCreateFile = (values: { fileType: string; fileName: string }) => {
    if (!id) return
    createFileMutation.mutate({
      name: values.fileName,
      type: values.fileType as 'file' | 'directory',
      path: currentPath
    })
    setIsCreateDialogOpen(false)
  }

  const handleBulkDelete = () => {
    if (selectedFiles.length === 0) {
      toast.warning('请选择要删除的文件')
      return
    }
    confirm({
      title: '确认删除',
      description: `确定要删除选中的 ${selectedFiles.length} 个文件吗？`,
      confirmText: '确定',
      cancelText: '取消',
      variant: 'destructive',
      onConfirm: async () => {
        if (id) {
          bulkDeleteMutation.mutate(selectedFiles)
          setSelectedFiles([])
        }
      },
    })
  }

  const handleMultiFileUploadComplete = () => {
    setSelectedUploadFiles([])
    setIsMultiFileUploadDialogOpen(false)
  }

  const handleRefresh = async () => {
    try {
      await refetch({ throwOnError: true })
      toast.success('刷新成功')
    } catch {
      toast.error('刷新失败')
    }
  }

  const handleArchiveSelect = async (filename: string) => {
    setIsArchiveDialogOpen(false)
    if (!id) return
    try {
      const result = await populateServerMutation.mutateAsync({
        serverId: id,
        archiveFilename: filename,
      })
      setPopulateTaskId(result.task_id)
      setIsPopulateProgressDialogOpen(true)
    } catch (error: any) {
      toast.error(`文件替换失败: ${error.message || '未知错误'}`)
    }
  }

  const handlePopulateComplete = () => {
    setIsPopulateProgressDialogOpen(false)
    setPopulateTaskId(null)
  }

  const handlePopulateClose = () => {
    setIsPopulateProgressDialogOpen(false)
    setPopulateTaskId(null)
  }

  const handleCompress = (file?: FileItem, compressionType?: 'file' | 'folder' | 'server') => {
    setCompressionFile(file || null)
    setCompressionType(compressionType || (file?.type === 'directory' ? 'folder' : 'file'))
    setIsCompressionConfirmDialogOpen(true)
  }

  const handleCompressionConfirm = async () => {
    if (!id) return

    let compressionPath: string | null = null
    switch (compressionType) {
      case 'file':
        compressionPath = compressionFile?.path || null
        break
      case 'folder':
        compressionPath = compressionFile?.path || currentPath
        break
      case 'server':
        compressionPath = null
        break
    }

    try {
      const result = await createArchiveMutation.mutateAsync({
        server_id: id,
        path: compressionPath
      })
      setCompressionTaskId(result.task_id)
    } catch (error: any) {
      toast.error(`压缩失败: ${error.message || '未知错误'}`)
    }
  }

  const handleDownloadCompressed = async () => {
    if (!compressionResult) return
    try {
      await downloadArchiveFile(`/${compressionResult.filename}`, compressionResult.filename)
    } catch (error: any) {
      toast.error(`下载失败: ${error.message || '未知错误'}`)
    }
  }

  const handleNavigateToParent = () => {
    const parentPath = currentPath.split('/').slice(0, -1).join('/') || '/'
    handleNavigateToPath(parentPath)
  }

  const handleCompressServer = () => handleCompress(undefined, 'server')
  const handleReplaceServerFiles = () => setIsArchiveDialogOpen(true)

  const handleRestoreOwnership = () => {
    confirm({
      title: '修复文件所有权',
      description: '将递归修改该服务器全部文件的 UID/GID，使其与服务器根目录一致。确定继续吗？',
      confirmText: '开始修复',
      cancelText: '取消',
      variant: 'destructive',
      onConfirm: async () => {
        if (id) {
          const result = await restoreOwnershipMutation.mutateAsync()
          setOwnershipTaskId(result.task_id)
        }
      },
    })
  }

  const handleDeepSearchNavigate = (path: string, query?: string, regex?: boolean) => {
    setIsDeepSearchDialogOpen(false)
    navigation.navigateSearchResult(path, query, regex)
  }

  return {
    id,
    filesError,
    fileData,
    isDragging,
    isScanning,
    hasServerInfo,
    serverInfo,
    currentPath,
    selectedFiles,
    isFetchingFiles,
    createArchiveMutation,
    populateServerMutation,
    bulkDeleteMutation,
    restoreOwnershipMutation,
    ownershipTask,
    handleNavigateToParent,
    handleRefresh,
    setIsMultiFileUploadDialogOpen,
    setIsCreateDialogOpen,
    handleBulkDelete,
    handleCompressServer,
    handleReplaceServerFiles,
    handleRestoreOwnership,
    refetch,
    handleNavigateToPath,
    searchBoxRef,
    inputSearchTerm,
    useRegex,
    handleSearchChange,
    handleRegexChange,
    handleSearchClear,
    handleSearch,
    setIsDeepSearchDialogOpen,
    filteredFileData,
    isLoadingFiles,
    setSelectedFiles,
    currentPage,
    pageSize,
    setCurrentPage,
    setPageSize,
    handleFileEdit,
    handleFileDelete,
    handleFileDownload,
    handleFileRename,
    handleFolderOpen,
    handleCompress,
    isMultiFileUploadDialogOpen,
    setSelectedUploadFiles,
    handleMultiFileUploadComplete,
    selectedUploadFiles,
    isCreateDialogOpen,
    handleCreateFile,
    createFileMutation,
    isRenameDialogOpen,
    setIsRenameDialogOpen,
    setRenamingFile,
    handleRenameSubmit,
    renamingFile,
    renameFileMutation,
    isEditDialogOpen,
    closeEditor,
    handleFileSave,
    handleShowDiff,
    editingFile,
    fileContent,
    setFileContent,
    originalFileContent,
    isLoadingContent,
    editorDraft,
    contentError,
    refetchContent,
    updateFileMutation,
    getCurrentFileLanguageConfig,
    isDiffDialogOpen,
    setIsDiffDialogOpen,
    isArchiveDialogOpen,
    setIsArchiveDialogOpen,
    handleArchiveSelect,
    isPopulateProgressDialogOpen,
    populateTaskId,
    handlePopulateClose,
    handlePopulateComplete,
    isCompressionConfirmDialogOpen,
    setIsCompressionConfirmDialogOpen,
    setCompressionFile,
    setCompressionTaskId,
    handleCompressionConfirm,
    compressionTask,
    compressionFile,
    compressionType,
    isCompressionResultDialogOpen,
    setIsCompressionResultDialogOpen,
    setCompressionResult,
    compressionResult,
    handleDownloadCompressed,
    isDeepSearchDialogOpen,
    handleDeepSearchNavigate,
    confirmDialog
  }
}
