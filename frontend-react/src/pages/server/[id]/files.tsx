import React, { useState } from 'react'
import { 
  Card, 
  Table, 
  Button, 
  Space, 
  Input,
  Modal, 
  Form, 
  Select, 
  App,
  Breadcrumb, 
  Typography, 
  Dropdown, 
  Tooltip,
  Alert,
  Popconfirm,
  Upload
} from 'antd'
import { 
  FolderOutlined, 
  FileOutlined, 
  EditOutlined, 
  DeleteOutlined, 
  DownloadOutlined, 
  PlusOutlined, 
  HomeOutlined,
  ReloadOutlined,
  FileTextOutlined,
  DatabaseOutlined,
  FileImageOutlined,
  FilePdfOutlined,
  FileZipOutlined,
  MoreOutlined,
  ArrowUpOutlined,
  UploadOutlined,
  DiffOutlined
} from '@ant-design/icons'
import { useParams, useNavigate, useLocation } from 'react-router-dom'
import { SimpleEditor, MonacoDiffEditor } from '@/components/editors'
import ServerStateTag from '@/components/overview/ServerStateTag'
import { useServerDetailQueries } from '@/hooks/queries/useServerDetailQueries'
import { useFileList, useFileContent, useFileOperations } from '@/hooks/queries/useFileQueries'
import type { FileItem } from '@/types/Server'

const { Title } = Typography
const { Option } = Select

const ServerFiles: React.FC = () => {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const location = useLocation()
  const [createForm] = Form.useForm()
  const [renameForm] = Form.useForm()
  const { message } = App.useApp()
  
  // Get server data for state tag
  const { useServerDetailData } = useServerDetailQueries(id || "")
  const { serverInfo, status, hasServerInfo } = useServerDetailData()
  
  // Get current path from URL search params
  const searchParams = new URLSearchParams(location.search)
  const currentPath = searchParams.get('path') || '/'
  
  // File management hooks
  const { data: fileData, isLoading: isLoadingFiles, error: filesError, refetch } = useFileList(id, currentPath)
  const {
    updateFile,
    uploadFile,
    createFile,
    deleteFile,
    renameFile,
    downloadFile,
    isUpdating,
    isUploading,
    isCreating,
    isDeleting,
    isRenaming
  } = useFileOperations(id)

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

  // Get file content for editing
  const { data: fileContentData, isLoading: isLoadingContent } = useFileContent(
    id, 
    editingFile?.path || null
  )

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

  const formatFileSize = (bytes: number) => {
    if (bytes === 0) return '-'
    const k = 1024
    const sizes = ['B', 'KB', 'MB', 'GB']
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
  }

  const formatDate = (timestamp: string) => {
    const date = new Date(parseFloat(timestamp) * 1000)
    return date.toLocaleString('zh-CN')
  }

  const getFileIcon = (file: FileItem) => {
    if (file.type === 'directory') {
      return <FolderOutlined style={{ color: '#1890ff' }} />
    }
    
    const ext = file.name.split('.').pop()?.toLowerCase()
    switch (ext) {
      case 'txt':
      case 'log':
      case 'yml':
      case 'yaml':
      case 'json':
      case 'properties':
        return <FileTextOutlined style={{ color: '#52c41a' }} />
      case 'png':
      case 'jpg':
      case 'jpeg':
      case 'gif':
        return <FileImageOutlined style={{ color: '#fa8c16' }} />
      case 'pdf':
        return <FilePdfOutlined style={{ color: '#f5222d' }} />
      case 'zip':
      case 'jar':
        return <FileZipOutlined style={{ color: '#722ed1' }} />
      case 'db':
      case 'sqlite':
        return <DatabaseOutlined style={{ color: '#13c2c2' }} />
      default:
        return <FileOutlined />
    }
  }

  const handleFileEdit = (file: FileItem) => {
    if (!file.is_editable) {
      message.warning('该文件不可编辑')
      return
    }
    setEditingFile(file)
    setIsEditModalVisible(true)
  }

  const handleFileSave = () => {
    if (editingFile && id) {
      updateFile({ path: editingFile.path, content: fileContent })
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
      deleteFile(file.path)
    }
  }

  const handleFileDownload = (file: FileItem) => {
    if (file.type === 'directory') {
      message.info('文件夹下载暂不开放')
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
      renameFile({
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
      createFile({
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
            deleteFile(filePath)
          })
          setSelectedFiles([])
        }
      }
    })
  }

  const handleUpload = () => {
    if (!id || uploadFileList.length === 0) return
    
    uploadFileList.forEach(fileItem => {
      uploadFile({ path: currentPath, file: fileItem.originFileObj })
    })
    setUploadFileList([])
    setIsUploadModalVisible(false)
  }

  const handleRefresh = async () => {
    try {
      await refetch()
      message.success('刷新成功')
    } catch (error) {
      message.error('刷新失败')
    }
  }

  const moreActions = (file: FileItem) => [
    {
      key: 'rename',
      label: '重命名',
      icon: <EditOutlined />,
      onClick: () => handleFileRename(file)
    }
  ]

  const columns = [
    {
      title: '文件名',
      dataIndex: 'name',
      key: 'name',
      render: (name: string, file: FileItem) => (
        <div className="flex items-center space-x-2">
          {getFileIcon(file)}
          <span 
            className={file.type === 'directory' ? 'font-medium cursor-pointer hover:text-blue-600' : 'font-medium'}
            onClick={() => file.type === 'directory' ? handleFolderOpen(file) : undefined}
          >
            {name}
          </span>
        </div>
      ),
    },
    {
      title: '大小',
      dataIndex: 'size',
      key: 'size',
      width: 100,
      render: (size: number) => formatFileSize(size),
    },
    {
      title: '修改时间',
      dataIndex: 'modified_at',
      key: 'modified_at',
      width: 180,
      render: (timestamp: string) => formatDate(timestamp),
    },
    {
      title: '操作',
      key: 'actions',
      width: 200,
      render: (_: any, file: FileItem) => (
        <Space>
          {file.type === 'directory' && (
            <Tooltip title="打开文件夹">
              <Button
                icon={<FolderOutlined />}
                size="small"
                onClick={() => handleFolderOpen(file)}
              />
            </Tooltip>
          )}
          {file.is_editable && (
            <Tooltip title="编辑文件">
              <Button
                icon={<EditOutlined />}
                size="small"
                onClick={() => handleFileEdit(file)}
              />
            </Tooltip>
          )}
          <Tooltip title="下载">
            <Button
              icon={<DownloadOutlined />}
              size="small"
              onClick={() => handleFileDownload(file)}
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
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <div className="flex items-center gap-3">
          <Title level={2} className="!mb-0 !mt-0">
            {hasServerInfo ? `${serverInfo?.name} - 文件管理` : "文件管理"}
          </Title>
          {status && <ServerStateTag state={status} />}
        </div>
        <Space>
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
              loading={isDeleting}
            >
              批量删除 ({selectedFiles.length})
            </Button>
          )}
        </Space>
      </div>

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
              onShowSizeChange: (current, size) => {
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
      <Modal
        title="上传文件"
        open={isUploadModalVisible}
        onOk={handleUpload}
        onCancel={() => {
          setIsUploadModalVisible(false)
          setUploadFileList([])
        }}
        okText="上传"
        cancelText="取消"
        confirmLoading={isUploading}
      >
        <Upload
          fileList={uploadFileList}
          onChange={({ fileList }) => setUploadFileList(fileList)}
          beforeUpload={() => false} // Prevent automatic upload
          multiple
        >
          <Button icon={<UploadOutlined />}>选择文件</Button>
        </Upload>
        <div className="mt-2 text-gray-500">
          文件将上传到当前目录: {currentPath}
        </div>
      </Modal>

      {/* 创建文件/文件夹模态框 */}
      <Modal
        title="新建文件/文件夹"
        open={isCreateModalVisible}
        onOk={handleCreateFile}
        onCancel={() => setIsCreateModalVisible(false)}
        okText="创建"
        cancelText="取消"
        confirmLoading={isCreating}
      >
        <Form form={createForm} layout="vertical">
          <Form.Item
            name="fileType"
            label="类型"
            rules={[{ required: true, message: '请选择文件类型' }]}
            initialValue="file"
          >
            <Select>
              <Option value="file">文件</Option>
              <Option value="directory">文件夹</Option>
            </Select>
          </Form.Item>
          <Form.Item
            name="fileName"
            label="名称"
            rules={[
              { required: true, message: '请输入文件名' },
              { pattern: /^[^<>:"/\\|?*]+$/, message: '文件名包含非法字符' }
            ]}
          >
            <Input placeholder="输入文件名或文件夹名" />
          </Form.Item>
        </Form>
      </Modal>

      {/* 重命名模态框 */}
      <Modal
        title="重命名"
        open={isRenameModalVisible}
        onOk={handleRenameSubmit}
        onCancel={() => {
          setIsRenameModalVisible(false)
          setRenamingFile(null)
          renameForm.resetFields()
        }}
        okText="确定"
        cancelText="取消"
        confirmLoading={isRenaming}
      >
        <Form form={renameForm} layout="vertical">
          <Form.Item
            name="newName"
            label="新名称"
            rules={[
              { required: true, message: '请输入新名称' },
              { pattern: /^[^<>:"/\\|?*]+$/, message: '名称包含非法字符' }
            ]}
          >
            <Input placeholder="输入新名称" />
          </Form.Item>
        </Form>
      </Modal>

      {/* 文件编辑模态框 */}
      <Modal
        title={`编辑文件: ${editingFile?.name}`}
        open={isEditModalVisible}
        onOk={handleFileSave}
        onCancel={() => {
          setIsEditModalVisible(false)
          setEditingFile(null)
          setFileContent('')
          setOriginalFileContent('')
        }}
        width={800}
        okText="保存"
        cancelText="取消"
        confirmLoading={isUpdating}
        footer={[
          <Button 
            key="diff" 
            icon={<DiffOutlined />} 
            onClick={handleShowDiff}
            disabled={!originalFileContent || fileContent === originalFileContent}
          >
            差异对比
          </Button>,
          <Button key="cancel" onClick={() => {
            setIsEditModalVisible(false)
            setEditingFile(null)
            setFileContent('')
            setOriginalFileContent('')
          }}>
            取消
          </Button>,
          <Button 
            key="save" 
            type="primary" 
            onClick={handleFileSave}
            loading={isUpdating}
          >
            保存
          </Button>,
        ]}
      >
        <div className="space-y-4">
          <Alert
            message="文件编辑"
            description="修改文件内容后点击保存。请谨慎编辑配置文件，错误的配置可能导致服务器无法启动。"
            type="warning"
            showIcon
          />
          {isLoadingContent ? (
            <div className="text-center py-8">加载文件内容中...</div>
          ) : (
            <SimpleEditor
              height="500px"
              language="text"
              value={fileContent}
              onChange={(value: string | undefined) => value !== undefined && setFileContent(value)}
              theme="vs-light"
            />
          )}
        </div>
      </Modal>

      {/* 文件差异对比模态框 */}
      <Modal
        title="文件差异对比"
        open={isDiffModalVisible}
        onCancel={() => setIsDiffModalVisible(false)}
        width={1400}
        footer={[
          <Button key="close" onClick={() => setIsDiffModalVisible(false)}>
            关闭
          </Button>
        ]}
      >
        <div className="space-y-4">
          <Alert
            message="差异对比视图"
            description="左侧为文件原始内容，右侧为当前编辑的内容。高亮显示的是差异部分。"
            type="info"
            showIcon
          />
          <div style={{ border: '1px solid #d9d9d9', borderRadius: '6px', overflow: 'hidden', height: '600px' }}>
            <MonacoDiffEditor
              height="600px"
              language="text"
              original={originalFileContent}
              modified={fileContent}
              originalTitle="文件原始内容"
              modifiedTitle="当前编辑内容"
              theme="vs-light"
            />
          </div>
        </div>
      </Modal>

      {/* 文件管理说明 */}
      <Alert
        message="文件管理说明"
        description="您可以浏览、编辑和管理服务器文件。点击文件夹名称或文件夹图标可以进入目录。配置文件可以直接编辑，其他文件可以下载查看。上传的文件将保存到当前目录中。"
        type="info"
        showIcon
        closable
      />
    </div>
  )
}

export default ServerFiles