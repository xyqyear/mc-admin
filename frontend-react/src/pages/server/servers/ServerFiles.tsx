import React, { useState } from 'react'
import {
  Card,
  Modal,
  Form,
  App,
  Alert
} from 'antd'
import {
  FolderOutlined
} from '@ant-design/icons'
import { useParams, useNavigate, useLocation } from 'react-router-dom'
import PageHeader from '@/components/layout/PageHeader'
import ArchiveSelectionModal from '@/components/modals/ArchiveSelectionModal'
import DragDropOverlay from '@/components/server/DragDropOverlay'
import {
  MultiFileUploadModal,
  CreateModal,
  RenameModal,
  FileEditModal,
  FileDiffModal,
  CompressionConfirmModal,
  CompressionResultModal
} from '@/components/modals/ServerFiles'
import { useServerDetailQueries } from '@/hooks/queries/page/useServerDetailQueries'
import { useFileList, useFileContent } from '@/hooks/queries/base/useFileQueries'
import { useFileMutations } from '@/hooks/mutations/useFileMutations'
import { useServerMutations } from '@/hooks/mutations/useServerMutations'
import { useArchiveMutations } from '@/hooks/mutations/useArchiveMutations'
import { detectFileLanguage, getLanguageEditorOptions, getComposeOverrideWarning, isFileEditable } from '@/config/fileEditingConfig'
import { usePageDragUpload } from '@/hooks/usePageDragUpload'
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
  const [createForm] = Form.useForm()
  const [renameForm] = Form.useForm()
  const { message } = App.useApp()

  // Get server data for page info - 只获取基础信息，不获取状态、资源等数据
  const { useServerFilesData } = useServerDetailQueries(id || "")
  const { serverInfo, hasServerInfo } = useServerFilesData()

  // Get current path and search params from URL
  const searchParams = new URLSearchParams(location.search)
  const currentPath = searchParams.get('path') || '/'
  const searchQuery = searchParams.get('q') || ''
  const useRegex = searchParams.get('regex') === 'true'

  // File management hooks
  const { data: fileData, isLoading: isLoadingFiles, error: filesError, refetch } = useFileList(id, currentPath)

  // Filter files based on search query
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

  // Initialize mutation hooks
  const updateFileMutation = useUpdateFile()
  const createFileMutation = useCreateFile()
  const deleteFileMutation = useDeleteFile()
  const bulkDeleteMutation = useBulkDeleteFiles()
  const renameFileMutation = useRenameFile()

  // Server mutation for populate
  const { usePopulateServer } = useServerMutations()
  const populateServerMutation = usePopulateServer()

  // Archive mutations for compression
  const { useCreateArchive, downloadFile: downloadArchiveFile } = useArchiveMutations()
  const createArchiveMutation = useCreateArchive()

  // Local state
  const [selectedFiles, setSelectedFiles] = useState<string[]>([])
  const [isCreateModalVisible, setIsCreateModalVisible] = useState(false)
  const [isEditModalVisible, setIsEditModalVisible] = useState(false)
  const [isMultiFileUploadModalVisible, setIsMultiFileUploadModalVisible] = useState(false)
  const [isRenameModalVisible, setIsRenameModalVisible] = useState(false)
  const [editingFile, setEditingFile] = useState<FileItem | null>(null)
  const [renamingFile, setRenamingFile] = useState<FileItem | null>(null)
  const [fileContent, setFileContent] = useState('')
  const [selectedUploadFiles, setSelectedUploadFiles] = useState<File[]>([])
  const [pageSize, setPageSize] = useState(20)
  const [currentPage, setCurrentPage] = useState(1)
  const [isDiffModalVisible, setIsDiffModalVisible] = useState(false)
  const [originalFileContent, setOriginalFileContent] = useState('')



  // Replace server files state
  const [isArchiveModalVisible, setIsArchiveModalVisible] = useState(false)

  // Compression modal states
  const [isCompressionConfirmModalVisible, setIsCompressionConfirmModalVisible] = useState(false)
  const [isCompressionResultModalVisible, setIsCompressionResultModalVisible] = useState(false)
  const [compressionFile, setCompressionFile] = useState<FileItem | null>(null)
  const [compressionType, setCompressionType] = useState<'file' | 'folder' | 'server'>('file')
  const [compressionResult, setCompressionResult] = useState<{ filename: string, message: string } | null>(null)

  // Search box ref for focusing
  const searchBoxRef = React.useRef<FileSearchBoxRef>(null)

  // Page drag upload
  const { isDragging, isScanning } = usePageDragUpload({
    onFileDrop: (files) => {
      console.log(`ServerFiles 接收到 ${files.length} 个文件:`)
      files.forEach((file, index) => {
        console.log(`  ${index + 1}. ${file.name} (${file.size} bytes) webkitRelativePath: ${(file as any).webkitRelativePath || 'none'}`)
      })
      setSelectedUploadFiles(files)
      setIsMultiFileUploadModalVisible(true)
      message.info(`已选择 ${files.length} 个文件，请确认上传`)
    },
    onError: (errorMessage) => {
      message.error(errorMessage)
    },
    allowDirectories: true  // 启用文件夹拖拽支持
  })

  // Get file content for editing
  const { data: fileContentData, isLoading: isLoadingContent } = useFileContent(
    id,
    editingFile?.path || null
  )

  // Get language configuration for the currently editing file
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

  // Update file content when data is loaded
  React.useEffect(() => {
    if (fileContentData && editingFile) {
      setFileContent(fileContentData.content)
      setOriginalFileContent(fileContentData.content) // 保存原始内容用于差异对比
    }
  }, [fileContentData, editingFile])

  // Reset pagination when path changes
  React.useEffect(() => {
    setCurrentPage(1)
  }, [currentPath])

  // Keyboard shortcut handler for Ctrl+F to focus search
  React.useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      // Check for Ctrl+F (Windows/Linux) or Cmd+F (Mac)
      if ((event.ctrlKey || event.metaKey) && event.key === 'f') {
        event.preventDefault()
        searchBoxRef.current?.focus()
      }
    }

    // Add event listener to document
    document.addEventListener('keydown', handleKeyDown)

    // Cleanup event listener on unmount
    return () => {
      document.removeEventListener('keydown', handleKeyDown)
    }
  }, [])

  // Update URL when path changes
  const updatePath = (newPath: string) => {
    const newSearchParams = new URLSearchParams(location.search)
    if (newPath === '/') {
      newSearchParams.delete('path')
    } else {
      newSearchParams.set('path', newPath)
    }
    // Clear search query when navigating to different path
    newSearchParams.delete('q')
    newSearchParams.delete('regex')

    const newSearch = newSearchParams.toString()
    const newUrl = `${location.pathname}${newSearch ? `?${newSearch}` : ''}`
    navigate(newUrl, { replace: false })
    setSelectedFiles([]) // Clear selection when navigating
  }

  // Update URL with search parameters
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
    const newUrl = `${location.pathname}${newSearch ? `?${newSearch}` : ''}`
    navigate(newUrl, { replace: true }) // Use replace to avoid cluttering history
  }

  // Search handlers
  const handleSearchChange = (term: string) => {
    updateSearchParams(term, useRegex)
  }

  const handleRegexChange = (regex: boolean) => {
    updateSearchParams(searchQuery, regex)
  }

  const handleSearchClear = () => {
    updateSearchParams('', false)
  }



  const handleFileEdit = (file: FileItem) => {
    if (!isFileEditable(file.name)) {
      message.warning('该文件不可编辑')
      return
    }
    setEditingFile(file)
    setIsEditModalVisible(true)
  }

  const handleFileSave = () => {
    if (editingFile && id) {
      updateFileMutation.mutate({ path: editingFile.path, content: fileContent })
      setIsEditModalVisible(false)
      setEditingFile(null)
      setFileContent('')
      setOriginalFileContent('')
    }
  }

  const handleShowDiff = () => {
    setIsDiffModalVisible(true)
  }

  const handleFileDelete = (file: FileItem) => {
    if (id) {
      deleteFileMutation.mutate(file.path)
    }
  }

  const handleFileDownload = (file: FileItem) => {
    if (file.type === 'directory') {
      message.info('请点击压缩按钮进行压缩下载')
      return
    }

    if (id) {
      downloadFile(file.path, file.name)
    }
  }

  const handleFileRename = (file: FileItem) => {
    setRenamingFile(file)
    renameForm.setFieldsValue({ newName: file.name })
    setIsRenameModalVisible(true)
  }

  const handleRenameSubmit = () => {
    if (!renamingFile || !id) return

    renameForm.validateFields().then(values => {
      renameFileMutation.mutate({
        old_path: renamingFile.path,
        new_name: values.newName
      })
      setIsRenameModalVisible(false)
      setRenamingFile(null)
      renameForm.resetFields()
    })
  }

  const handleFolderOpen = (folder: FileItem) => {
    if (folder.type === 'directory') {
      updatePath(folder.path)
    }
  }

  const handleNavigateToPath = (path: string) => {
    updatePath(path)
  }

  const handleCreateFile = () => {
    if (!id) return

    createForm.validateFields().then(values => {
      createFileMutation.mutate({
        name: values.fileName,
        type: values.fileType,
        path: currentPath
      })
      setIsCreateModalVisible(false)
      createForm.resetFields()
    })
  }

  const handleBulkDelete = () => {
    if (selectedFiles.length === 0) {
      message.warning('请选择要删除的文件')
      return
    }

    Modal.confirm({
      title: '确认删除',
      content: `确定要删除选中的 ${selectedFiles.length} 个文件吗？`,
      onOk: () => {
        if (id) {
          bulkDeleteMutation.mutate(selectedFiles)
          setSelectedFiles([])
        }
      }
    })
  }

  const handleMultiFileUploadComplete = () => {
    setSelectedUploadFiles([])
    setIsMultiFileUploadModalVisible(false)
    refetch() // Refresh file list
  }

  const handleRefresh = async () => {
    try {
      await refetch()
      message.success('刷新成功')
    } catch {
      message.error('刷新失败')
    }
  }

  // Replace server files handlers
  const handleArchiveSelect = async (filename: string) => {
    setIsArchiveModalVisible(false)
    message.success(`已选择压缩包: ${filename}`)

    if (!id) return

    try {
      // 直接使用mutation进行服务器文件替换
      await populateServerMutation.mutateAsync({
        serverId: id,
        archiveFilename: filename,
      })
      message.success('服务器文件替换完成!')
      // Refresh file list to show new files
      refetch()
    } catch (error: any) {
      message.error(`文件替换失败: ${error.message || '未知错误'}`)
    }
  }

  // Compression handlers
  const handleCompress = (file?: FileItem, compressionType?: 'file' | 'folder' | 'server') => {
    setCompressionFile(file || null)
    setCompressionType(compressionType || (file?.type === 'directory' ? 'folder' : 'file'))
    setIsCompressionConfirmModalVisible(true)
  }

  const handleCompressionConfirm = async () => {
    if (!id) return

    let compressionPath: string | null = null

    // Determine compression path based on type
    switch (compressionType) {
      case 'file':
        compressionPath = compressionFile?.path || null
        break
      case 'folder':
        compressionPath = compressionFile?.path || currentPath
        break
      case 'server':
        compressionPath = null // null means compress entire server
        break
    }

    try {
      const result = await createArchiveMutation.mutateAsync({
        server_id: id,
        path: compressionPath
      })

      setCompressionResult({
        filename: result.archive_filename,
        message: result.message
      })

      setIsCompressionConfirmModalVisible(false)
      setIsCompressionResultModalVisible(true)
      setCompressionFile(null)
    } catch (error: any) {
      message.error(`压缩失败: ${error.message || '未知错误'}`)
    }
  }

  const handleDownloadCompressed = async () => {
    if (!compressionResult) return

    try {
      await downloadArchiveFile(`/${compressionResult.filename}`, compressionResult.filename)
    } catch (error: any) {
      message.error(`下载失败: ${error.message || '未知错误'}`)
    }
  }

  // 工具栏事件处理函数
  const handleNavigateToParent = () => {
    const parentPath = currentPath.split('/').slice(0, -1).join('/') || '/'
    handleNavigateToPath(parentPath)
  }

  const handleCompressServer = () => {
    handleCompress(undefined, 'server')
  }

  const handleReplaceServerFiles = () => {
    setIsArchiveModalVisible(true)
  }

  if (filesError) {
    return <div>加载文件列表失败: {filesError.message}</div>
  }

  return (
    <div className="space-y-4">
      {/* 拖拽覆盖层 */}
      <DragDropOverlay
        isDragging={isDragging}
        isScanning={isScanning}
        allowDirectories={true}
        pageType="serverFiles"
      />

      <PageHeader
        title="文件"
        icon={<FolderOutlined />}
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
            onUpload={() => setIsMultiFileUploadModalVisible(true)}
            onCreateFile={() => setIsCreateModalVisible(true)}
            onBulkDelete={handleBulkDelete}
            onCompressServer={handleCompressServer}
            onReplaceServerFiles={handleReplaceServerFiles}
            onRefreshSnapshot={refetch}
          />
        }
      />

      <Card>
        <div className="space-y-4">
          {/* Breadcrumb and Search */}
          <div className="flex items-center justify-between gap-4">
            <FileBreadcrumb
              currentPath={currentPath}
              onNavigateToPath={handleNavigateToPath}
            />
            <div className="flex-shrink-0 min-w-[300px] max-w-md">
              <FileSearchBox
                ref={searchBoxRef}
                searchTerm={searchQuery}
                useRegex={useRegex}
                onSearchChange={handleSearchChange}
                onRegexChange={handleRegexChange}
                onClear={handleSearchClear}
                placeholder="搜索当前文件夹..."
              />
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
        </div>
      </Card>

      {/* 多文件上传模态框 */}
      <MultiFileUploadModal
        open={isMultiFileUploadModalVisible}
        onCancel={() => {
          setIsMultiFileUploadModalVisible(false)
          setSelectedUploadFiles([])
        }}
        onComplete={handleMultiFileUploadComplete}
        serverId={id || ''}
        basePath={currentPath}
        initialFiles={selectedUploadFiles}
      />

      {/* 创建文件/文件夹模态框 */}
      <CreateModal
        open={isCreateModalVisible}
        onCancel={() => setIsCreateModalVisible(false)}
        onOk={handleCreateFile}
        form={createForm}
        confirmLoading={createFileMutation.isPending}
      />

      {/* 重命名模态框 */}
      <RenameModal
        open={isRenameModalVisible}
        onCancel={() => {
          setIsRenameModalVisible(false)
          setRenamingFile(null)
          renameForm.resetFields()
        }}
        onOk={handleRenameSubmit}
        form={renameForm}
        confirmLoading={renameFileMutation.isPending}
      />

      {/* 文件编辑模态框 */}
      <FileEditModal
        open={isEditModalVisible}
        onCancel={() => {
          setIsEditModalVisible(false)
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

      {/* 文件差异对比模态框 */}
      <FileDiffModal
        open={isDiffModalVisible}
        onCancel={() => setIsDiffModalVisible(false)}
        originalFileContent={originalFileContent}
        fileContent={fileContent}
        serverId={id || ''}
        getCurrentFileLanguageConfig={getCurrentFileLanguageConfig}
      />


      {/* 文件管理说明 */}
      <Alert
        message="文件管理说明"
        description="您可以浏览、编辑和管理服务器文件。点击文件夹名称或文件夹图标可以进入目录。配置文件可以直接编辑，其他文件可以下载查看。上传的文件将保存到当前目录中。"
        type="info"
        showIcon
        closable
      />

      {/* 压缩包选择弹窗 */}
      <ArchiveSelectionModal
        open={isArchiveModalVisible}
        onCancel={() => setIsArchiveModalVisible(false)}
        onSelect={handleArchiveSelect}
        title="选择压缩包文件"
        description="选择要用于替换服务器文件的压缩包文件"
        selectButtonText="替换服务器文件"
        selectButtonType="danger"
      />

      {/* 压缩确认弹窗 */}
      <CompressionConfirmModal
        open={isCompressionConfirmModalVisible}
        onCancel={() => {
          setIsCompressionConfirmModalVisible(false)
          setCompressionFile(null)
        }}
        onOk={handleCompressionConfirm}
        confirmLoading={createArchiveMutation.isPending}
        selectedFile={compressionFile}
        currentPath={currentPath}
        compressionType={compressionType}
        serverName={hasServerInfo ? serverInfo?.name : ''}
      />

      {/* 压缩结果弹窗 */}
      <CompressionResultModal
        open={isCompressionResultModalVisible}
        onCancel={() => {
          setIsCompressionResultModalVisible(false)
          setCompressionResult(null)
        }}
        archiveFilename={compressionResult?.filename || ''}
        message={compressionResult?.message || ''}
        onDownload={handleDownloadCompressed}
        downloadLoading={false}
      />

    </div>
  )
}

export default ServerFiles