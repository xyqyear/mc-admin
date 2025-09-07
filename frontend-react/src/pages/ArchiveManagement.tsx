import React, { useState, useRef } from 'react'
import {
  Card,
  Table,
  Button,
  Space,
  Modal,
  Form,
  Input,
  App,
  Popconfirm,
  Upload,
  Tooltip,
  Switch,
  Alert,
  Dropdown,
  Progress
} from 'antd'
import {
  DeleteOutlined,
  DownloadOutlined,
  ReloadOutlined,
  UploadOutlined,
  FileOutlined,
  FolderOutlined,
  FileZipOutlined,
  MoreOutlined
} from '@ant-design/icons'
import { SimpleEditor } from '@/components/editors'
import PageHeader from '@/components/layout/PageHeader'
import { useArchiveQueries } from '@/hooks/queries/base/useArchiveQueries'
import { useArchiveMutations } from '@/hooks/mutations/useArchiveMutations'
import { formatFileSize, formatDate, formatBytes } from '@/utils/formatUtils'
import { detectFileLanguage, isFileEditable } from '@/config/fileEditingConfig'
import type { ArchiveFileItem } from '@/hooks/api/archiveApi'
import type { ColumnType } from 'antd/es/table/interface'

const ArchiveManagement: React.FC = () => {
  const { message } = App.useApp()
  const [renameForm] = Form.useForm()

  // Archive management hooks
  const { useArchiveFileList, useArchiveFileContent } = useArchiveQueries()
  const {
    useUploadFile,
    useDeleteItem,
    useRenameItem,
    useUpdateFileContent,
    downloadFile,
  } = useArchiveMutations()

  // Query data
  const { data: fileData, isLoading, refetch } = useArchiveFileList()
  const archiveFiles = fileData?.items || []

  // Initialize mutation hooks
  const uploadFileMutation = useUploadFile()
  const deleteItemMutation = useDeleteItem()
  const renameItemMutation = useRenameItem()
  const updateFileMutation = useUpdateFileContent()

  // Local state
  const [selectedFiles, setSelectedFiles] = useState<string[]>([])
  const [isEditModalVisible, setIsEditModalVisible] = useState(false)
  const [isRenameModalVisible, setIsRenameModalVisible] = useState(false)
  const [isUploadModalVisible, setIsUploadModalVisible] = useState(false)
  const [editingFile, setEditingFile] = useState<ArchiveFileItem | null>(null)
  const [renamingFile, setRenamingFile] = useState<ArchiveFileItem | null>(null)
  const [fileContent, setFileContent] = useState('')
  const [uploadFileList, setUploadFileList] = useState<any[]>([])
  const [allowOverwrite, setAllowOverwrite] = useState(false)
  const [pageSize, setPageSize] = useState(20)
  const [currentPage, setCurrentPage] = useState(1)
  
  // Upload progress tracking
  const [uploadProgress, setUploadProgress] = useState<number>(0)
  const [uploadSpeed, setUploadSpeed] = useState<string>('0 B/s')
  const [isUploading, setIsUploading] = useState<boolean>(false)
  const uploadBytesHistory = useRef<Array<{time: number, bytes: number}>>([])
  const speedUpdateTimer = useRef<NodeJS.Timeout | null>(null)
  const uploadAbortController = useRef<AbortController | null>(null)

  // Get file content for editing
  const { data: fileContentData } = useArchiveFileContent(
    editingFile?.path || null
  )

  // Update file content when data changes
  React.useEffect(() => {
    if (fileContentData?.content !== undefined) {
      setFileContent(fileContentData.content)
    }
  }, [fileContentData])

  // Handle file operations
  const handleDownload = async (file: ArchiveFileItem) => {
    await downloadFile(file.path, file.name)
  }

  const handleDelete = async (file: ArchiveFileItem) => {
    try {
      await deleteItemMutation.mutateAsync(file.path)
    } catch {
      // Error is handled by mutation
    }
  }

  const handleEdit = (file: ArchiveFileItem) => {
    if (!isFileEditable(file.name)) {
      message.warning('此文件类型不支持编辑')
      return
    }
    setEditingFile(file)
    setIsEditModalVisible(true)
  }

  const handleSaveFile = async () => {
    if (!editingFile) return

    try {
      await updateFileMutation.mutateAsync({
        path: editingFile.path,
        content: fileContent,
      })
      setIsEditModalVisible(false)
      setEditingFile(null)
    } catch {
      // Error is handled by mutation
    }
  }

  const handleRenameItem = async (values: any) => {
    if (!renamingFile) return

    try {
      await renameItemMutation.mutateAsync({
        old_path: renamingFile.path,
        new_name: values.new_name,
      })
      setIsRenameModalVisible(false)
      setRenamingFile(null)
      renameForm.resetFields()
    } catch {
      // Error is handled by mutation
    }
  }


  const calculateSpeed = (loadedBytes: number): string => {
    const now = Date.now()
    const history = uploadBytesHistory.current
    
    // Add current data point
    history.push({ time: now, bytes: loadedBytes })
    
    // Keep only data points from last 5 seconds
    const fiveSecondsAgo = now - 5000
    uploadBytesHistory.current = history.filter(point => point.time >= fiveSecondsAgo)
    
    if (uploadBytesHistory.current.length < 2) return '0 B/s'
    
    // Calculate speed using oldest and newest data points in the window
    const oldest = uploadBytesHistory.current[0]
    const newest = uploadBytesHistory.current[uploadBytesHistory.current.length - 1]
    const timeDiff = (newest.time - oldest.time) / 1000 // seconds
    const bytesDiff = newest.bytes - oldest.bytes
    
    if (timeDiff <= 0) return '0 B/s'
    
    const speed = bytesDiff / timeDiff
    return `${formatBytes(speed)}/s`
  }

  const handleUploadWithProgress = async (file: File) => {
    // Create AbortController for this upload
    const controller = new AbortController()
    uploadAbortController.current = controller
    
    // Initialize tracking
    setIsUploading(true)
    uploadBytesHistory.current = []
    setUploadProgress(0)
    setUploadSpeed('0 B/s')
    
    try {
      await uploadFileMutation.mutateAsync({
        path: '/',
        file,
        allowOverwrite,
        options: {
          signal: controller.signal,
          onUploadProgress: (progressEvent) => {
            const percent = Math.round(progressEvent.progress)
            setUploadProgress(percent)
            
            const speed = calculateSpeed(progressEvent.loaded)
            setUploadSpeed(speed)
          }
        }
      })
      
      // Clean up on success
      uploadAbortController.current = null
      setIsUploading(false)
      uploadBytesHistory.current = []
      setUploadProgress(0)
      setUploadSpeed('0 B/s')
    } catch (error: any) {
      // Clean up on error or cancellation
      uploadAbortController.current = null
      setIsUploading(false)
      uploadBytesHistory.current = []
      setUploadProgress(0)
      setUploadSpeed('0 B/s')
      
      // Check if error is due to cancellation
      if (error.name === 'CanceledError' || error.code === 'ERR_CANCELED') {
        // Request was cancelled, don't show error message
        return
      }
      
      // Re-throw other errors to be handled by mutation's onError
      throw error
    }
  }

  const hasValidFiles = uploadFileList.some(file => {
    const fileName = file.name.toLowerCase()
    return fileName.endsWith('.zip') || fileName.endsWith('.7z')
  })
  
  // Unified cleanup function for upload modal
  const cleanupUploadModal = () => {
    // Cancel ongoing upload request if exists
    if (uploadAbortController.current) {
      uploadAbortController.current.abort()
      uploadAbortController.current = null
    }
    
    setIsUploadModalVisible(false)
    setUploadFileList([])
    setAllowOverwrite(false)
    // Clear progress tracking
    setUploadProgress(0)
    setUploadSpeed('0 B/s')
    setIsUploading(false)
    uploadBytesHistory.current = []
    if (speedUpdateTimer.current) {
      clearInterval(speedUpdateTimer.current)
      speedUpdateTimer.current = null
    }
  }

  // Clean up timer on component unmount
  React.useEffect(() => {
    return () => {
      if (speedUpdateTimer.current) {
        clearInterval(speedUpdateTimer.current)
      }
    }
  }, [])

  const handleBulkDelete = () => {
    if (selectedFiles.length === 0) {
      message.warning('请选择要删除的文件')
      return
    }

    Modal.confirm({
      title: '确认删除',
      content: `确定要删除选中的 ${selectedFiles.length} 个文件吗？`,
      onOk: async () => {
        try {
          for (const filePath of selectedFiles) {
            await deleteItemMutation.mutateAsync(filePath)
          }
          setSelectedFiles([])
        } catch {
          // Error is handled by mutation
        }
      }
    })
  }

  const handleRefresh = async () => {
    try {
      await refetch()
      message.success('刷新成功')
    } catch {
      message.error('刷新失败')
    }
  }

  const moreActions = (file: ArchiveFileItem) => [
    {
      key: 'rename',
      label: '重命名',
      onClick: () => {
        setRenamingFile(file)
        renameForm.setFieldValue('new_name', file.name)
        setIsRenameModalVisible(true)
      }
    }
  ]

  // Table columns
  const columns: ColumnType<ArchiveFileItem>[] = [
    {
      title: '文件名',
      dataIndex: 'name',
      key: 'name',
      render: (name: string, file: ArchiveFileItem) => {
        const isEditable = isFileEditable(file.name)
        const isDirectory = file.type === 'directory'

        return (
          <div className="flex items-center space-x-2">
            {isDirectory ? (
              <FolderOutlined style={{ color: '#1677ff' }} />
            ) : (
              <FileOutlined style={{ color: '#52c41a' }} />
            )}
            <Tooltip title={isEditable ? '点击编辑文件' : undefined}>
              <span
                className={
                  isEditable ? 'font-medium cursor-pointer text-blue-600 hover:text-blue-800' :
                    'font-medium'
                }
                onClick={() => {
                  if (isEditable) {
                    handleEdit(file)
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
      render: (size: number, record: ArchiveFileItem) =>
        record.type === 'file' ? formatFileSize(size) : '-',
    },
    {
      title: '修改时间',
      dataIndex: 'modified_at',
      key: 'modified_at',
      width: 150,
      render: (modified_at: number) => formatDate(modified_at),
    },
    {
      title: '操作',
      key: 'actions',
      width: 200,
      render: (_, file: ArchiveFileItem) => (
        <Space size="small">
          {file.type === 'file' && (
            <Tooltip title="下载">
              <Button
                icon={<DownloadOutlined />}
                size="small"
                onClick={() => handleDownload(file)}
              />
            </Tooltip>
          )}
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
            title={`确定要删除 ${file.name} 吗？`}
            onConfirm={() => handleDelete(file)}
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

  return (
    <div className="space-y-4">
      <PageHeader
        title="压缩包管理"
        icon={<FileZipOutlined />}
        actions={
          <>
            <Button
              icon={<UploadOutlined />}
              onClick={() => setIsUploadModalVisible(true)}
            >
              上传文件
            </Button>
            <Button
              icon={<ReloadOutlined />}
              onClick={handleRefresh}
              loading={isLoading}
            >
              刷新
            </Button>
            {selectedFiles.length > 0 && (
              <Button
                icon={<DeleteOutlined />}
                danger
                onClick={handleBulkDelete}
                loading={deleteItemMutation.isPending}
              >
                批量删除 ({selectedFiles.length})
              </Button>
            )}
          </>
        }
      />

      <Card>
        <div className="space-y-4">
          <Table
            dataSource={archiveFiles}
            columns={columns}
            rowKey="path"
            size="small"
            loading={isLoading}
            rowSelection={{
              selectedRowKeys: selectedFiles,
              onChange: (selectedRowKeys: React.Key[]) => {
                setSelectedFiles(selectedRowKeys as string[])
              },
              getCheckboxProps: (record: ArchiveFileItem) => ({
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
                  setCurrentPage(1)
                }
              },
              onShowSizeChange: (_, size) => {
                setPageSize(size)
                setCurrentPage(1)
              }
            }}
            locale={{ emptyText: '暂无文件' }}
          />
        </div>
      </Card>

      {/* 文件编辑模态框 */}
      <Modal
        title={`编辑文件: ${editingFile?.name}`}
        open={isEditModalVisible}
        onOk={handleSaveFile}
        onCancel={() => {
          setIsEditModalVisible(false)
          setEditingFile(null)
        }}
        width={800}
        okText="保存"
        cancelText="取消"
        confirmLoading={updateFileMutation.isPending}
      >
        <div className="space-y-4">
          <Alert
            message="文件编辑"
            description="修改文件内容后点击保存。请谨慎编辑配置文件，错误的配置可能导致文件损坏。"
            type="warning"
            showIcon
          />
          <div style={{ height: '500px' }}>
            <SimpleEditor
              height="500px"
              language={editingFile ? detectFileLanguage(editingFile.name).language : 'text'}
              value={fileContent}
              onChange={(value: string | undefined) => value !== undefined && setFileContent(value)}
              theme="vs-light"
            />
          </div>
        </div>
      </Modal>

      {/* 重命名模态框 */}
      <Modal
        title="重命名"
        open={isRenameModalVisible}
        onOk={() => renameForm.submit()}
        onCancel={() => {
          setIsRenameModalVisible(false)
          setRenamingFile(null)
          renameForm.resetFields()
        }}
        okText="确定"
        cancelText="取消"
        confirmLoading={renameItemMutation.isPending}
      >
        <Form
          form={renameForm}
          layout="vertical"
          onFinish={handleRenameItem}
        >
          <Form.Item
            name="new_name"
            label="新名称"
            rules={[
              { required: true, message: '请输入新名称' },
              { max: 255, message: '名称不能超过255个字符' },
              { pattern: /^[^<>:"/\\|?*]+$/, message: '名称包含非法字符' }
            ]}
          >
            <Input placeholder="输入新名称" />
          </Form.Item>
        </Form>
      </Modal>

      {/* 上传文件模态框 */}
      <Modal
        title="上传文件"
        open={isUploadModalVisible}
        footer={[
          <Button 
            key="upload"
            type="primary"
            onClick={async () => {
              const validFiles = uploadFileList.filter(file => {
                const fileName = file.name.toLowerCase()
                return fileName.endsWith('.zip') || fileName.endsWith('.7z')
              })
              
              if (validFiles.length === 0) {
                message.warning('请选择要上传的压缩包文件')
                return
              }
              
              // Upload files sequentially to show progress for each
              for (const fileItem of validFiles) {
                if (fileItem.originFileObj) {
                  await handleUploadWithProgress(fileItem.originFileObj)
                }
              }
              
              // Close modal and cleanup after successful upload
              cleanupUploadModal()
            }}
            loading={uploadFileMutation.isPending || isUploading}
            disabled={!hasValidFiles || isUploading}
          >
            开始上传
          </Button>,
          <Button 
            key="cancel" 
            onClick={cleanupUploadModal}
          >
            关闭
          </Button>
        ]}
        onCancel={cleanupUploadModal}
      >
        <div className="space-y-4">
          <Upload
            fileList={uploadFileList}
            onChange={({ fileList }) => setUploadFileList(fileList)}
            beforeUpload={(file) => {
              const isZipOrSevenZ = file.name.toLowerCase().endsWith('.zip') || file.name.toLowerCase().endsWith('.7z')
              if (!isZipOrSevenZ) {
                message.error(`${file.name} 不是支持的压缩包格式，只支持 .zip 和 .7z 格式`)
                return false
              }
              return false // Prevent automatic upload, we handle it manually
            }}
            accept=".zip,.7z"
            multiple
            showUploadList={{
              showPreviewIcon: false,
              showDownloadIcon: false,
              showRemoveIcon: true
            }}
          >
            <Button icon={<UploadOutlined />}>选择压缩包文件</Button>
          </Upload>
          <div className="mt-2 text-gray-500">
            仅支持 .zip 和 .7z 格式的压缩包文件
          </div>
          
          {isUploading && (
            <div className="mt-4">
              <Progress 
                percent={uploadProgress} 
                size="default" 
                format={() => `${uploadProgress}% - ${uploadSpeed}`}
              />
            </div>
          )}
          
          <div className="flex items-center space-x-2">
            <Switch
              checked={allowOverwrite}
              onChange={setAllowOverwrite}
            />
            <span>允许覆盖同名文件</span>
          </div>
        </div>
      </Modal>

      {/* 压缩包管理说明 */}
      <Alert
        message="压缩包管理说明"
        description="您可以浏览、编辑和管理压缩包内的文件。可编辑的文件支持直接在线编辑，其他文件可以下载查看。上传的文件将保存到压缩包根目录中。"
        type="info"
        showIcon
        closable
      />
    </div>
  )
}

export default ArchiveManagement