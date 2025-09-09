import React, { useState } from 'react'
import {
  Card,
  Table,
  Button,
  Space,
  Modal,
  Form,
  App,
  Breadcrumb,
  Dropdown,
  Tooltip,
  Alert,
  Popconfirm
} from 'antd'
import {
  DeleteOutlined,
  DownloadOutlined,
  PlusOutlined,
  HomeOutlined,
  ReloadOutlined,
  MoreOutlined,
  ArrowUpOutlined,
  UploadOutlined,
  FolderOutlined,
  FileZipOutlined
} from '@ant-design/icons'
import { useParams, useNavigate, useLocation } from 'react-router-dom'
import FileIcon from '@/components/files/FileIcon'
import PageHeader from '@/components/layout/PageHeader'
import ArchiveSelectionModal from '@/components/modals/ArchiveSelectionModal'
import {
  UploadModal,
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
import { formatFileSize, formatDate } from '@/utils/formatUtils'
import FileSnapshotActions from '@/components/files/FileSnapshotActions'
import { usePageDragUpload } from '@/hooks/usePageDragUpload'
import type { FileItem } from '@/types/Server'
import type { SortOrder, ColumnType } from 'antd/es/table/interface'

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

  // Get current path from URL search params
  const searchParams = new URLSearchParams(location.search)
  const currentPath = searchParams.get('path') || '/'

  // File management hooks
  const { data: fileData, isLoading: isLoadingFiles, error: filesError, refetch } = useFileList(id, currentPath)
  const {
    useUpdateFile,
    useUploadFile,
    useCreateFile,
    useDeleteFile,
    useRenameFile,
    downloadFile
  } = useFileMutations(id)

  // Initialize mutation hooks
  const updateFileMutation = useUpdateFile()
  const uploadFileMutation = useUploadFile()
  const createFileMutation = useCreateFile()
  const deleteFileMutation = useDeleteFile()
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
  const [isUploadModalVisible, setIsUploadModalVisible] = useState(false)
  const [isRenameModalVisible, setIsRenameModalVisible] = useState(false)
  const [editingFile, setEditingFile] = useState<FileItem | null>(null)
  const [renamingFile, setRenamingFile] = useState<FileItem | null>(null)
  const [fileContent, setFileContent] = useState('')
  const [uploadFileList, setUploadFileList] = useState<any[]>([])
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
  const [compressionResult, setCompressionResult] = useState<{filename: string, message: string} | null>(null)

  // Page drag upload
  const { isDragging } = usePageDragUpload({
    onFileDrop: (files) => {
      // 转换为上传文件列表格式
      const fileList = files.map((file, index) => ({
        uid: `${Date.now()}-${index}`,
        name: file.name,
        status: 'done' as const,
        originFileObj: file,
      }))
      setUploadFileList(fileList)
      setIsUploadModalVisible(true)
      message.info(`已选择 ${files.length} 个文件，请确认上传`)
    },
    onError: (errorMessage) => {
      message.error(errorMessage)
    }
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

  // Update URL when path changes
  const updatePath = (newPath: string) => {
    const newSearchParams = new URLSearchParams(location.search)
    if (newPath === '/') {
      newSearchParams.delete('path')
    } else {
      newSearchParams.set('path', newPath)
    }
    const newSearch = newSearchParams.toString()
    const newUrl = `${location.pathname}${newSearch ? `?${newSearch}` : ''}`
    navigate(newUrl, { replace: false })
    setSelectedFiles([]) // Clear selection when navigating
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
          selectedFiles.forEach(filePath => {
            deleteFileMutation.mutate(filePath)
          })
          setSelectedFiles([])
        }
      }
    })
  }

  const handleUpload = () => {
    if (!id || uploadFileList.length === 0) return

    uploadFileList.forEach(fileItem => {
      uploadFileMutation.mutate({ path: currentPath, file: fileItem.originFileObj })
    })
    setUploadFileList([])
    setIsUploadModalVisible(false)
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

  const moreActions = (file: FileItem) => [
    {
      key: 'rename',
      label: '重命名',
      onClick: () => handleFileRename(file)
    },
    {
      key: 'compress',
      label: '压缩',
      onClick: () => handleCompress(file)
    }
  ]

  const columns: ColumnType<FileItem>[] = [
    {
      title: '文件名',
      dataIndex: 'name',
      key: 'name',
      sorter: (a: FileItem, b: FileItem) => {
        // Custom sorting: directories first, then files, both alphabetically
        if (a.type !== b.type) {
          return a.type === 'directory' ? -1 : 1
        }
        return a.name.localeCompare(b.name, 'zh-CN', { sensitivity: 'base' })
      },
      sortDirections: ['ascend', 'descend'] as SortOrder[],
      defaultSortOrder: 'ascend' as SortOrder,
      render: (name: string, file: FileItem) => {
        const isEditable = isFileEditable(file.name)
        const isDirectory = file.type === 'directory'

        return (
          <div className="flex items-center space-x-2">
            <FileIcon file={file} />
            <Tooltip
              title={
                isDirectory ? '点击打开文件夹' :
                  isEditable ? '点击编辑文件' :
                    undefined
              }
            >
              <span
                className={
                  isDirectory ? 'font-medium cursor-pointer hover:text-blue-600' :
                    isEditable ? 'font-medium cursor-pointer text-blue-600 hover:text-blue-800' :
                      'font-medium'
                }
                onClick={() => {
                  if (isDirectory) {
                    handleFolderOpen(file)
                  } else if (isEditable) {
                    handleFileEdit(file)
                  }
                }}
              >
                {name}
              </span>
            </Tooltip>
          </div>
        )
      },
    },
    {
      title: '大小',
      dataIndex: 'size',
      key: 'size',
      width: 90,
      sorter: (a: FileItem, b: FileItem) => a.size - b.size,
      sortDirections: ['ascend', 'descend'] as SortOrder[],
      render: (size: number) => formatFileSize(size),
    },
    {
      title: '修改时间',
      dataIndex: 'modified_at',
      key: 'modified_at',
      width: 150,
      sorter: (a: FileItem, b: FileItem) => a.modified_at - b.modified_at,
      sortDirections: ['ascend', 'descend'] as SortOrder[],
      render: (timestamp: number) => formatDate(timestamp),
    },
    {
      title: '操作',
      key: 'actions',
      width: 200,
      render: (_: any, file: FileItem) => (
        <Space size="small">
          {/* 快照操作按钮 */}
          <FileSnapshotActions file={file} serverId={id || ''} />

          <Tooltip title="下载">
            <Button
              icon={<DownloadOutlined />}
              size="small"
              onClick={() => handleFileDownload(file)}
            />
          </Tooltip>
          <Tooltip title="压缩">
            <Button
              icon={<FileZipOutlined />}
              size="small"
              onClick={() => handleCompress(file)}
              loading={createArchiveMutation.isPending}
            />
          </Tooltip>
          <Dropdown
            menu={{
              items: moreActions(file).map(action => ({
                ...action,
                onClick: action.onClick
              }))
            }}
            trigger={['click']}
          >
            <Button size="small" icon={<MoreOutlined />} />
          </Dropdown>
          <Popconfirm
            title="确定要删除这个文件吗？"
            onConfirm={() => handleFileDelete(file)}
            okText="确定"
            cancelText="取消"
          >
            <Button
              icon={<DeleteOutlined />}
              size="small"
              danger
            />
          </Popconfirm>
        </Space>
      ),
    },
  ]

  const pathSegments = currentPath.split('/').filter(Boolean)

  if (filesError) {
    return <div>加载文件列表失败: {filesError.message}</div>
  }

  return (
    <div className={`space-y-4 ${isDragging ? 'relative' : ''}`}>
      {/* 拖拽覆盖层 */}
      {isDragging && (
        <div className="fixed inset-0 bg-blue-500 bg-opacity-10 border-2 border-dashed border-blue-500 z-50 flex items-center justify-center">
          <div className="bg-white rounded-lg shadow-lg p-8 text-center">
            <UploadOutlined className="text-4xl text-blue-500 mb-4" />
            <div className="text-xl font-medium text-blue-600 mb-2">拖拽文件到此处上传</div>
            <div className="text-gray-500">松开鼠标完成文件选择</div>
          </div>
        </div>
      )}
      <PageHeader
        title="文件"
        icon={<FolderOutlined />}
        serverTag={hasServerInfo ? serverInfo?.name : undefined}
        actions={
          <>
            {currentPath !== '/' && (
              <Button
                icon={<ArrowUpOutlined />}
                onClick={() => {
                  const parentPath = currentPath.split('/').slice(0, -1).join('/') || '/'
                  handleNavigateToPath(parentPath)
                }}
              >
                返回上级
              </Button>
            )}
            {currentPath === '/' && (
              <>
                <FileSnapshotActions 
                  serverId={id || ''} 
                  path="/" 
                  isServerMode={true} 
                  onRefresh={refetch} 
                />
                <Button
                  icon={<FileZipOutlined />}
                  onClick={() => handleCompress(undefined, 'server')}
                  loading={createArchiveMutation.isPending}
                >
                  打包服务器
                </Button>
                <Button
                  icon={<FileZipOutlined />}
                  danger
                  onClick={() => setIsArchiveModalVisible(true)}
                  loading={populateServerMutation.isPending}
                >
                  替换服务器文件
                </Button>
              </>
            )}
            <Button
              icon={<UploadOutlined />}
              onClick={() => setIsUploadModalVisible(true)}
            >
              上传文件
            </Button>
            <Button
              icon={<PlusOutlined />}
              onClick={() => setIsCreateModalVisible(true)}
            >
              新建文件/文件夹
            </Button>
            <Button
              icon={<ReloadOutlined />}
              onClick={handleRefresh}
              loading={isLoadingFiles}
            >
              刷新
            </Button>
            {selectedFiles.length > 0 && (
              <Button
                icon={<DeleteOutlined />}
                danger
                onClick={handleBulkDelete}
                loading={deleteFileMutation.isPending}
              >
                批量删除 ({selectedFiles.length})
              </Button>
            )}
          </>
        }
      />

      <Card>
        <div className="space-y-4">
          <Breadcrumb
            items={[
              {
                title: (
                  <>
                    <HomeOutlined />
                    <span
                      className="cursor-pointer ml-1"
                      onClick={() => handleNavigateToPath('/')}
                    >
                      根目录
                    </span>
                  </>
                )
              },
              ...pathSegments.map((segment, index) => ({
                title: (
                  <span
                    className="cursor-pointer"
                    onClick={() => handleNavigateToPath('/' + pathSegments.slice(0, index + 1).join('/'))}
                  >
                    {segment}
                  </span>
                )
              }))
            ]}
          />

          <Table
            dataSource={fileData?.items || []}
            columns={columns}
            rowKey="path"
            size="small"
            loading={isLoadingFiles}
            rowSelection={{
              selectedRowKeys: selectedFiles,
              onChange: (selectedRowKeys: React.Key[]) => {
                setSelectedFiles(selectedRowKeys as string[])
              },
              getCheckboxProps: (record: FileItem) => ({
                name: record.name,
              }),
            }}
            pagination={{
              current: currentPage,
              pageSize: pageSize,
              showSizeChanger: true,
              showQuickJumper: true,
              pageSizeOptions: ['10', '20', '50', '100'],
              showTotal: (total, range) => `${range[0]}-${range[1]} 共 ${total} 个文件`,
              simple: false,
              size: "default",
              onChange: (page, size) => {
                setCurrentPage(page)
                if (size !== pageSize) {
                  setPageSize(size)
                  setCurrentPage(1) // Reset to first page when page size changes
                }
              },
              onShowSizeChange: (_, size) => {
                setPageSize(size)
                setCurrentPage(1) // Reset to first page when page size changes
              }
            }}
            onRow={(record) => ({
              onDoubleClick: () => {
                if (record.type === 'directory') {
                  handleFolderOpen(record)
                }
              }
            })}
          />
        </div>
      </Card>

      {/* 上传文件模态框 */}
      <UploadModal
        open={isUploadModalVisible}
        onCancel={() => setIsUploadModalVisible(false)}
        onOk={handleUpload}
        currentPath={currentPath}
        uploadFileList={uploadFileList}
        setUploadFileList={setUploadFileList}
        confirmLoading={uploadFileMutation.isPending}
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