import React, { useState, useEffect } from 'react'
import { toast } from 'sonner'
import { Folder, Search } from 'lucide-react'
import { useParams, useNavigate, useLocation } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'

import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Alert, AlertTitle, AlertDescription } from '@/components/ui/alert'

import PageHeader from '@/components/layout/PageHeader'
import ArchiveSelectionDialog from '@/components/dialogs/ArchiveSelectionDialog'
import PopulateProgressDialog from '@/components/dialogs/PopulateProgressDialog'
import DragDropOverlay from '@/components/server/DragDropOverlay'
import {
  MultiFileUploadDialog,
  CreateDialog,
  RenameDialog,
  FileEditDialog,
  FileDiffDialog,
  CompressionConfirmDialog,
  CompressionResultDialog,
  FileDeepSearchDialog
} from '@/components/dialogs/ServerFiles'
import { useServerDetailQueries } from '@/hooks/queries/page/useServerDetailQueries'
import { useFileList, useFileContent } from '@/hooks/queries/base/useFileQueries'
import { useTaskQueries } from '@/hooks/queries/base/useTaskQueries'
import { useFileMutations } from '@/hooks/mutations/useFileMutations'
import { useServerMutations } from '@/hooks/mutations/useServerMutations'
import { useArchiveMutations } from '@/hooks/mutations/useArchiveMutations'
import { detectFileLanguage, getLanguageEditorOptions, getComposeOverrideWarning, isFileEditable } from '@/config/fileEditingConfig'
import { usePageDragUpload } from '@/hooks/usePageDragUpload'
import { useConfirm } from '@/hooks/useConfirm'
import { queryKeys } from '@/utils/api'
import FileTable from '@/components/server/FileTable'
import FileToolbar from '@/components/server/FileToolbar'
import FileBreadcrumb from '@/components/server/FileBreadcrumb'
import FileSearchBox, { FileSearchBoxRef } from '@/components/server/FileSearchBox'
import { searchFiles } from '@/utils/fileSearchUtils'
import type { FileItem } from '@/types/Server'

const ServerFiles: React.FC = () => {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const location = useLocation()
  const queryClient = useQueryClient()
  const { confirm, confirmDialog } = useConfirm()

  const { useServerFilesData } = useServerDetailQueries(id || "")
  const { serverInfo, hasServerInfo } = useServerFilesData()

  const searchParams = new URLSearchParams(location.search)
  const currentPath = searchParams.get('path') || '/'
  const searchQuery = searchParams.get('q') || ''
  const useRegex = searchParams.get('regex') === 'true'

  const [inputSearchTerm, setInputSearchTerm] = useState(searchQuery)

  const { data: fileData, isLoading: isLoadingFiles, error: filesError, refetch } = useFileList(id, currentPath)

  const filteredFileData = React.useMemo(() => {
    if (!fileData?.items || !searchQuery.trim()) {
      return fileData
    }
    const filteredItems = searchFiles(fileData.items, searchQuery, useRegex)
    return { ...fileData, items: filteredItems }
  }, [fileData, searchQuery, useRegex])

  const {
    useUpdateFile,
    useCreateFile,
    useDeleteFile,
    useBulkDeleteFiles,
    useRenameFile,
    downloadFile
  } = useFileMutations(id)

  const updateFileMutation = useUpdateFile()
  const createFileMutation = useCreateFile()
  const deleteFileMutation = useDeleteFile()
  const bulkDeleteMutation = useBulkDeleteFiles()
  const renameFileMutation = useRenameFile()

  const { usePopulateServer } = useServerMutations()
  const populateServerMutation = usePopulateServer()

  const { useCreateArchive, downloadFile: downloadArchiveFile } = useArchiveMutations()
  const createArchiveMutation = useCreateArchive()

  const { useTask } = useTaskQueries()

  // Local state
  const [selectedFiles, setSelectedFiles] = useState<string[]>([])
  const [isCreateDialogOpen, setIsCreateDialogOpen] = useState(false)
  const [isEditDialogOpen, setIsEditDialogOpen] = useState(false)
  const [isMultiFileUploadDialogOpen, setIsMultiFileUploadDialogOpen] = useState(false)
  const [isRenameDialogOpen, setIsRenameDialogOpen] = useState(false)
  const [editingFile, setEditingFile] = useState<FileItem | null>(null)
  const [renamingFile, setRenamingFile] = useState<FileItem | null>(null)
  const [fileContent, setFileContent] = useState('')
  const [selectedUploadFiles, setSelectedUploadFiles] = useState<File[]>([])
  const [pageSize, setPageSize] = useState(20)
  const [currentPage, setCurrentPage] = useState(1)
  const [isDiffDialogOpen, setIsDiffDialogOpen] = useState(false)
  const [originalFileContent, setOriginalFileContent] = useState('')

  const [isArchiveDialogOpen, setIsArchiveDialogOpen] = useState(false)
  const [populateTaskId, setPopulateTaskId] = useState<string | null>(null)
  const [isPopulateProgressDialogOpen, setIsPopulateProgressDialogOpen] = useState(false)

  const [isCompressionConfirmDialogOpen, setIsCompressionConfirmDialogOpen] = useState(false)
  const [isCompressionResultDialogOpen, setIsCompressionResultDialogOpen] = useState(false)
  const [compressionFile, setCompressionFile] = useState<FileItem | null>(null)
  const [compressionType, setCompressionType] = useState<'file' | 'folder' | 'server'>('file')
  const [compressionResult, setCompressionResult] = useState<{ filename: string, message: string } | null>(null)
  const [compressionTaskId, setCompressionTaskId] = useState<string | null>(null)

  const { data: compressionTask } = useTask(compressionTaskId || '')

  const [isDeepSearchDialogOpen, setIsDeepSearchDialogOpen] = useState(false)
  const searchBoxRef = React.useRef<FileSearchBoxRef>(null)

  // Page drag upload
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

  const { data: fileContentData, isLoading: isLoadingContent } = useFileContent(
    id,
    editingFile?.path || null
  )

  const getCurrentFileLanguageConfig = () => {
    if (!editingFile) return { language: 'text', options: {}, config: undefined, composeWarning: undefined }
    const languageConfig = detectFileLanguage(editingFile.name)
    const editorOptions = getLanguageEditorOptions(languageConfig.language)
    const composeWarning = getComposeOverrideWarning(editingFile.name)
    return {
      language: languageConfig.language,
      options: editorOptions,
      config: languageConfig,
      composeWarning: composeWarning.shouldWarn ? composeWarning : undefined
    }
  }

  React.useEffect(() => {
    if (fileContentData && editingFile) {
      setFileContent(fileContentData.content)
      setOriginalFileContent(fileContentData.content)
    }
  }, [fileContentData, editingFile])

  React.useEffect(() => {
    setCurrentPage(1)
  }, [currentPath])

  React.useEffect(() => {
    setInputSearchTerm(searchQuery)
  }, [searchQuery])

  // Watch for compression task completion
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
      queryClient.invalidateQueries({ queryKey: queryKeys.archive.files('/') })
    } else if (compressionTask.status === 'failed') {
      toast.error(`压缩失败: ${compressionTask.error}`)
      setCompressionTaskId(null)
    } else if (compressionTask.status === 'cancelled') {
      toast.info('压缩任务已取消')
      setCompressionTaskId(null)
    }
  }, [compressionTask, compressionTaskId, queryClient])

  // Ctrl+F to focus search
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

  const updatePath = (newPath: string) => {
    const newSearchParams = new URLSearchParams(location.search)
    if (newPath === '/') {
      newSearchParams.delete('path')
    } else {
      newSearchParams.set('path', newPath)
    }
    newSearchParams.delete('q')
    newSearchParams.delete('regex')
    const newSearch = newSearchParams.toString()
    navigate(`${location.pathname}${newSearch ? `?${newSearch}` : ''}`, { replace: false })
    setSelectedFiles([])
  }

  const updateSearchParams = (query: string, regex: boolean) => {
    const newSearchParams = new URLSearchParams(location.search)
    if (query.trim()) {
      newSearchParams.set('q', query)
    } else {
      newSearchParams.delete('q')
    }
    if (regex) {
      newSearchParams.set('regex', 'true')
    } else {
      newSearchParams.delete('regex')
    }
    const newSearch = newSearchParams.toString()
    navigate(`${location.pathname}${newSearch ? `?${newSearch}` : ''}`, { replace: true })
  }

  const handleSearchChange = (term: string) => setInputSearchTerm(term)
  const handleSearch = (term: string, regex: boolean) => updateSearchParams(term, regex)
  const handleRegexChange = (regex: boolean) => updateSearchParams(inputSearchTerm, regex)
  const handleSearchClear = () => {
    setInputSearchTerm('')
    updateSearchParams('', false)
  }

  const handleFileEdit = (file: FileItem) => {
    if (!isFileEditable(file.name)) {
      toast.warning('该文件不可编辑')
      return
    }
    setEditingFile(file)
    setIsEditDialogOpen(true)
  }

  const handleFileSave = () => {
    if (editingFile && id) {
      updateFileMutation.mutate({ path: editingFile.path, content: fileContent })
      setIsEditDialogOpen(false)
      setEditingFile(null)
      setFileContent('')
      setOriginalFileContent('')
    }
  }

  const handleShowDiff = () => setIsDiffDialogOpen(true)

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
    refetch()
  }

  const handleRefresh = async () => {
    try {
      await refetch()
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
    refetch()
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

  const handleDeepSearchNavigate = (path: string, query?: string, regex?: boolean) => {
    setIsDeepSearchDialogOpen(false)
    const newSearchParams = new URLSearchParams(location.search)
    if (path === '/') {
      newSearchParams.delete('path')
    } else {
      newSearchParams.set('path', path)
    }
    if (query && query.trim()) {
      newSearchParams.set('q', query)
      newSearchParams.set('regex', regex ? 'true' : 'false')
      setInputSearchTerm(query)
    } else {
      newSearchParams.delete('q')
      newSearchParams.delete('regex')
      setInputSearchTerm('')
    }
    const newSearch = newSearchParams.toString()
    navigate(`${location.pathname}${newSearch ? `?${newSearch}` : ''}`, { replace: false })
    setSelectedFiles([])
  }

  if (filesError) {
    return <div className="text-destructive">加载文件列表失败: {filesError.message}</div>
  }

  return (
    <div className="space-y-4">
      <DragDropOverlay
        isDragging={isDragging}
        isScanning={isScanning}
        allowDirectories={true}
        pageType="serverFiles"
      />

      <PageHeader
        title="文件"
        icon={<Folder className="h-5 w-5" />}
        serverTag={hasServerInfo ? serverInfo?.name : undefined}
        actions={
          <FileToolbar
            currentPath={currentPath}
            selectedFiles={selectedFiles}
            serverId={id || ''}
            isLoadingFiles={isLoadingFiles}
            createArchiveMutation={createArchiveMutation}
            populateServerMutation={populateServerMutation}
            bulkDeleteMutation={bulkDeleteMutation}
            onNavigateToParent={handleNavigateToParent}
            onRefresh={handleRefresh}
            onUpload={() => setIsMultiFileUploadDialogOpen(true)}
            onCreateFile={() => setIsCreateDialogOpen(true)}
            onBulkDelete={handleBulkDelete}
            onCompressServer={handleCompressServer}
            onReplaceServerFiles={handleReplaceServerFiles}
            onRefreshSnapshot={refetch}
          />
        }
      />

      <Card>
        <CardContent className="space-y-4">
          {/* Breadcrumb and Search */}
          <div className="flex items-center justify-between gap-4">
            <FileBreadcrumb
              currentPath={currentPath}
              onNavigateToPath={handleNavigateToPath}
            />
            <div className="flex items-center gap-2">
              <div className="shrink-0 min-w-75 max-w-md">
                <FileSearchBox
                  ref={searchBoxRef}
                  searchTerm={inputSearchTerm}
                  useRegex={useRegex}
                  onSearchChange={handleSearchChange}
                  onRegexChange={handleRegexChange}
                  onClear={handleSearchClear}
                  onSearch={handleSearch}
                  placeholder="按回车键搜索当前文件夹..."
                />
              </div>
              <Button
                variant="outline"
                onClick={() => setIsDeepSearchDialogOpen(true)}
              >
                <Search className="mr-2 h-4 w-4" />
                高级搜索
              </Button>
            </div>
          </div>

          <FileTable
            fileData={filteredFileData}
            isLoadingFiles={isLoadingFiles}
            selectedFiles={selectedFiles}
            setSelectedFiles={setSelectedFiles}
            currentPage={currentPage}
            pageSize={pageSize}
            setCurrentPage={setCurrentPage}
            setPageSize={setPageSize}
            serverId={id || ''}
            onFileEdit={handleFileEdit}
            onFileDelete={handleFileDelete}
            onFileDownload={handleFileDownload}
            onFileRename={handleFileRename}
            onFolderOpen={handleFolderOpen}
            onFileCompress={handleCompress}
            createArchiveMutation={createArchiveMutation}
          />
        </CardContent>
      </Card>

      <MultiFileUploadDialog
        open={isMultiFileUploadDialogOpen}
        onCancel={() => {
          setIsMultiFileUploadDialogOpen(false)
          setSelectedUploadFiles([])
        }}
        onComplete={handleMultiFileUploadComplete}
        serverId={id || ''}
        basePath={currentPath}
        initialFiles={selectedUploadFiles}
      />

      <CreateDialog
        open={isCreateDialogOpen}
        onCancel={() => setIsCreateDialogOpen(false)}
        onSubmit={handleCreateFile}
        confirmLoading={createFileMutation.isPending}
      />

      <RenameDialog
        open={isRenameDialogOpen}
        onCancel={() => {
          setIsRenameDialogOpen(false)
          setRenamingFile(null)
        }}
        onSubmit={handleRenameSubmit}
        initialName={renamingFile?.name}
        confirmLoading={renameFileMutation.isPending}
      />

      <FileEditDialog
        open={isEditDialogOpen}
        onCancel={() => {
          setIsEditDialogOpen(false)
          setEditingFile(null)
          setFileContent('')
          setOriginalFileContent('')
        }}
        onSave={handleFileSave}
        onShowDiff={handleShowDiff}
        editingFile={editingFile}
        fileContent={fileContent}
        setFileContent={setFileContent}
        originalFileContent={originalFileContent}
        isLoadingContent={isLoadingContent}
        confirmLoading={updateFileMutation.isPending}
        serverId={id || ''}
        getCurrentFileLanguageConfig={getCurrentFileLanguageConfig}
      />

      <FileDiffDialog
        open={isDiffDialogOpen}
        onCancel={() => setIsDiffDialogOpen(false)}
        originalFileContent={originalFileContent}
        fileContent={fileContent}
        serverId={id || ''}
        getCurrentFileLanguageConfig={getCurrentFileLanguageConfig}
      />

      <Alert>
        <AlertTitle>文件管理说明</AlertTitle>
        <AlertDescription>
          您可以浏览、编辑和管理服务器文件。点击文件夹名称或文件夹图标可以进入目录。配置文件可以直接编辑，其他文件可以下载查看。上传的文件将保存到当前目录中。
        </AlertDescription>
      </Alert>

      <ArchiveSelectionDialog
        open={isArchiveDialogOpen}
        onCancel={() => setIsArchiveDialogOpen(false)}
        onSelect={handleArchiveSelect}
        title="选择压缩包文件"
        description="选择要用于替换服务器文件的压缩包文件"
        selectButtonText="替换服务器文件"
        selectButtonType="danger"
      />

      <PopulateProgressDialog
        open={isPopulateProgressDialogOpen}
        taskId={populateTaskId}
        serverId={id || ''}
        onClose={handlePopulateClose}
        onComplete={handlePopulateComplete}
      />

      <CompressionConfirmDialog
        open={isCompressionConfirmDialogOpen}
        onCancel={() => {
          setIsCompressionConfirmDialogOpen(false)
          setCompressionFile(null)
          setCompressionTaskId(null)
        }}
        onOk={handleCompressionConfirm}
        confirmLoading={createArchiveMutation.isPending}
        task={compressionTask}
        selectedFile={compressionFile}
        currentPath={currentPath}
        compressionType={compressionType}
        serverName={hasServerInfo ? serverInfo?.name : ''}
      />

      <CompressionResultDialog
        open={isCompressionResultDialogOpen}
        onCancel={() => {
          setIsCompressionResultDialogOpen(false)
          setCompressionResult(null)
        }}
        archiveFilename={compressionResult?.filename || ''}
        message={compressionResult?.message || ''}
        onDownload={handleDownloadCompressed}
        downloadLoading={false}
      />

      <FileDeepSearchDialog
        open={isDeepSearchDialogOpen}
        onCancel={() => setIsDeepSearchDialogOpen(false)}
        serverId={id || ''}
        currentPath={currentPath}
        onNavigate={handleDeepSearchNavigate}
      />

      {confirmDialog}
    </div>
  )
}

export default ServerFiles
