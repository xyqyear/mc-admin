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
  message, 
  Breadcrumb, 
  Typography, 
  Dropdown, 
  Tooltip,
  Tag,
  Alert,
  Popconfirm
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
  CopyOutlined,
  CloudDownloadOutlined,
  ArrowUpOutlined
} from '@ant-design/icons'
import { useParams, useNavigate, useLocation } from 'react-router-dom'
import { SimpleEditor } from '@/components/editors'
import type { FileItem } from '@/types/Server'

const { Title } = Typography
const { Option } = Select

// Mock file data - expanded with nested structure
const mockAllFiles: FileItem[] = [
  // Root files
  {
    name: 'server.properties',
    type: 'file',
    size: 2048,
    modifiedAt: '2025-08-27T10:00:00Z',
    isConfig: true,
    isEditable: true,
    path: '/server.properties'
  },
  {
    name: 'bukkit.yml',
    type: 'file',
    size: 1536,
    modifiedAt: '2025-08-27T08:45:00Z',
    isConfig: true,
    isEditable: true,
    path: '/bukkit.yml'
  },
  // Root directories
  {
    name: 'world',
    type: 'directory',
    size: 0,
    modifiedAt: '2025-08-27T09:30:00Z',
    isConfig: false,
    isEditable: false,
    path: '/world'
  },
  {
    name: 'plugins',
    type: 'directory',
    size: 0,
    modifiedAt: '2025-08-27T09:15:00Z',
    isConfig: false,
    isEditable: false,
    path: '/plugins'
  },
  {
    name: 'logs',
    type: 'directory',
    size: 0,
    modifiedAt: '2025-08-27T08:00:00Z',
    isConfig: false,
    isEditable: false,
    path: '/logs'
  },
  // Files in /world
  {
    name: 'level.dat',
    type: 'file',
    size: 8192,
    modifiedAt: '2025-08-27T07:00:00Z',
    isConfig: false,
    isEditable: false,
    path: '/world/level.dat'
  },
  {
    name: 'region',
    type: 'directory',
    size: 0,
    modifiedAt: '2025-08-27T06:30:00Z',
    isConfig: false,
    isEditable: false,
    path: '/world/region'
  },
  {
    name: 'data',
    type: 'directory',
    size: 0,
    modifiedAt: '2025-08-27T06:00:00Z',
    isConfig: false,
    isEditable: false,
    path: '/world/data'
  },
  // Files in /plugins
  {
    name: 'EssentialsX.jar',
    type: 'file',
    size: 1048576,
    modifiedAt: '2025-08-26T15:00:00Z',
    isConfig: false,
    isEditable: false,
    path: '/plugins/EssentialsX.jar'
  },
  {
    name: 'WorldEdit.jar',
    type: 'file',
    size: 2097152,
    modifiedAt: '2025-08-26T14:30:00Z',
    isConfig: false,
    isEditable: false,
    path: '/plugins/WorldEdit.jar'
  },
  {
    name: 'Essentials',
    type: 'directory',
    size: 0,
    modifiedAt: '2025-08-26T14:00:00Z',
    isConfig: false,
    isEditable: false,
    path: '/plugins/Essentials'
  },
  // Files in /logs
  {
    name: 'latest.log',
    type: 'file',
    size: 65536,
    modifiedAt: '2025-08-27T11:00:00Z',
    isConfig: false,
    isEditable: true,
    path: '/logs/latest.log'
  },
  {
    name: '2025-08-26-1.log.gz',
    type: 'file',
    size: 32768,
    modifiedAt: '2025-08-26T23:59:59Z',
    isConfig: false,
    isEditable: false,
    path: '/logs/2025-08-26-1.log.gz'
  },
  // Files in nested directories
  {
    name: 'r.0.0.mca',
    type: 'file',
    size: 4194304,
    modifiedAt: '2025-08-26T10:00:00Z',
    isConfig: false,
    isEditable: false,
    path: '/world/region/r.0.0.mca'
  },
  {
    name: 'config.yml',
    type: 'file',
    size: 1024,
    modifiedAt: '2025-08-26T13:00:00Z',
    isConfig: true,
    isEditable: true,
    path: '/plugins/Essentials/config.yml'
  }
]

const ServerFiles: React.FC = () => {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const location = useLocation()
  const [form] = Form.useForm()
  const [allFiles] = useState<FileItem[]>(mockAllFiles)
  const [selectedFiles, setSelectedFiles] = useState<string[]>([])
  const [isCreateModalVisible, setIsCreateModalVisible] = useState(false)
  const [isEditModalVisible, setIsEditModalVisible] = useState(false)
  const [editingFile, setEditingFile] = useState<FileItem | null>(null)
  const [fileContent, setFileContent] = useState('')

  // Get current path from URL search params
  const searchParams = new URLSearchParams(location.search)
  const currentPath = searchParams.get('path') || '/'

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
    navigate(newUrl, { replace: false }) // Use push instead of replace to create history
    setSelectedFiles([]) // Clear selection when navigating
  }

  // Filter files based on current path
  const currentFiles = allFiles.filter(file => {
    const filePath = file.path
    const pathParts = filePath.split('/').filter(Boolean)
    const currentParts = currentPath.split('/').filter(Boolean)
    
    // If we're at root, show only files and directories directly in root
    if (currentPath === '/') {
      return pathParts.length === 1
    }
    
    // Check if file is in current directory
    if (pathParts.length === currentParts.length + 1) {
      return pathParts.slice(0, currentParts.length).join('/') === currentParts.join('/')
    }
    
    return false
  })

  const formatFileSize = (bytes: number) => {
    if (bytes === 0) return '-'
    const k = 1024
    const sizes = ['B', 'KB', 'MB', 'GB']
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
  }

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleString('zh-CN')
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
    setEditingFile(file)
    setFileContent(`# 示例文件内容 - ${file.name}\n# 这里是模拟的文件内容\n\n`)
    setIsEditModalVisible(true)
  }

  const handleFileSave = () => {
    if (editingFile) {
      message.success(`文件 ${editingFile.name} 保存成功`)
      setIsEditModalVisible(false)
      setEditingFile(null)
      setFileContent('')
    }
  }

  const handleFileDelete = (file: FileItem) => {
    // In a real implementation, this would need to remove from allFiles
    message.success(`文件 ${file.name} 删除成功`)
    message.info('注意：这是演示版本，文件不会真正删除')
  }

  const handleFileDownload = (file: FileItem) => {
    message.info(`开始下载 ${file.name}`)
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
    form.validateFields().then(values => {
      // In a real implementation, this would create a new file in allFiles
      setIsCreateModalVisible(false)
      form.resetFields()
      message.success(`${values.fileType === 'file' ? '文件' : '文件夹'} ${values.fileName} 创建成功`)
      message.info('注意：这是演示版本，文件不会真正创建')
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
        // In a real implementation, this would update allFiles
        setSelectedFiles([])
        message.success(`成功删除 ${selectedFiles.length} 个文件`)
        message.info('注意：这是演示版本，文件不会真正删除')
      }
    })
  }

  const moreActions = (file: FileItem) => [
    {
      key: 'copy',
      label: '复制',
      icon: <CopyOutlined />,
      onClick: () => message.info(`复制 ${file.name}`)
    },
    {
      key: 'backup',
      label: '备份',
      icon: <CloudDownloadOutlined />,
      onClick: () => message.info(`备份 ${file.name}`)
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
          <div className="flex space-x-1">
            {file.isConfig && <Tag color="blue">配置</Tag>}
            {file.isEditable && <Tag color="green">可编辑</Tag>}
          </div>
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
      dataIndex: 'lastModified',
      key: 'lastModified',
      width: 180,
      render: (date: string) => formatDate(date),
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
          {file.isEditable && (
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

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <Title level={2} className="!mb-0 !mt-0">{id} - 文件管理</Title>
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
            icon={<PlusOutlined />}
            onClick={() => setIsCreateModalVisible(true)}
          >
            新建文件/文件夹
          </Button>
          <Button
            icon={<ReloadOutlined />}
            onClick={() => message.info('刷新文件列表')}
          >
            刷新
          </Button>
          {selectedFiles.length > 0 && (
            <Button
              icon={<DeleteOutlined />}
              danger
              onClick={handleBulkDelete}
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

          <Alert
            message="文件管理说明"
            description="您可以浏览、编辑和管理服务器文件。点击文件夹名称或文件夹图标可以进入目录。配置文件可以直接编辑，其他文件可以下载查看。"
            type="info"
            showIcon
            closable
          />

          <Table
            dataSource={currentFiles}
            columns={columns}
            rowKey="name"
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
              pageSize: 20,
              showSizeChanger: true,
              showQuickJumper: true,
              showTotal: (total, range) => `${range[0]}-${range[1]} 共 ${total} 个文件`
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

      {/* 创建文件/文件夹模态框 */}
      <Modal
        title="新建文件/文件夹"
        open={isCreateModalVisible}
        onOk={handleCreateFile}
        onCancel={() => setIsCreateModalVisible(false)}
        okText="创建"
        cancelText="取消"
      >
        <Form form={form} layout="vertical">
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

      {/* 文件编辑模态框 */}
      <Modal
        title={`编辑文件: ${editingFile?.name}`}
        open={isEditModalVisible}
        onOk={handleFileSave}
        onCancel={() => setIsEditModalVisible(false)}
        width={800}
        okText="保存"
        cancelText="取消"
      >
        <div className="space-y-4">
          <Alert
            message="文件编辑"
            description="修改文件内容后点击保存。请谨慎编辑配置文件，错误的配置可能导致服务器无法启动。"
            type="warning"
            showIcon
          />
          <SimpleEditor
            height="500px"
            language="text"
            value={fileContent}
            onChange={(value: string | undefined) => value !== undefined && setFileContent(value)}
            theme="vs-light"
          />
        </div>
      </Modal>
    </div>
  )
}
export default ServerFiles
