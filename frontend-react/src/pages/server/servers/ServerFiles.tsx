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
  Dropdown,
  Tooltip,
  Alert,
  Popconfirm,
  Upload
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
  DiffOutlined,
  FolderOutlined
} from '@ant-design/icons'
import { useParams, useNavigate, useLocation } from 'react-router-dom'
import { SimpleEditor, MonacoDiffEditor } from '@/components/editors'
import FileIcon from '@/components/files/FileIcon'
import PageHeader from '@/components/layout/PageHeader'
import { useServerDetailQueries } from '@/hooks/queries/page/useServerDetailQueries'
import { useFileList, useFileContent } from '@/hooks/queries/base/useFileQueries'
import { useFileMutations } from '@/hooks/mutations/useFileMutations'
import { detectFileLanguage, getLanguageEditorOptions, getComposeOverrideWarning, isFileEditable } from '@/config/fileEditingConfig'
import { formatFileSize, formatDate } from '@/utils/formatUtils'
import FileSnapshotActions from '@/components/files/FileSnapshotActions'
import type { FileItem } from '@/types/Server'
import type { SortOrder, ColumnType } from 'antd/es/table/interface'

const { Option } = Select

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
    } catch (error) {
      message.error('刷新失败')
    }
  }

  const moreActions = (file: FileItem) => [
    {
      key: 'rename',
      label: '重命名',
      onClick: () => handleFileRename(file)
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
        confirmLoading={uploadFileMutation.isPending}
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
        confirmLoading={createFileMutation.isPending}
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
        confirmLoading={renameFileMutation.isPending}
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
        confirmLoading={updateFileMutation.isPending}
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
            loading={updateFileMutation.isPending}
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
            (() => {
              const { language, options, config, composeWarning } = getCurrentFileLanguageConfig()
              return (
                <div className="space-y-3">
                  {/* Compose override warning */}
                  {composeWarning && (
                    <Alert
                      message={composeWarning.title}
                      description={
                        <div className="space-y-2">
                          <p>{composeWarning.message}</p>
                          <Button
                            type="link"
                            size="small"
                            className="p-0 h-auto"
                            onClick={() => navigate(`/server/${id}/compose`)}
                          >
                            {composeWarning.linkText}
                          </Button>
                        </div>
                      }
                      type={composeWarning.severity}
                      showIcon
                      closable
                    />
                  )}

                  {/* Language support indicator */}
                  {config?.supportsValidation && (
                    <div className="text-xs text-gray-500 px-2">
                      <span className="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-blue-100 text-blue-800">
                        {config?.description} - 支持语法检查
                      </span>
                    </div>
                  )}

                  <SimpleEditor
                    height="500px"
                    language={language}
                    value={fileContent}
                    onChange={(value: string | undefined) => value !== undefined && setFileContent(value)}
                    theme="vs-light"
                    options={options}
                  />
                </div>
              )
            })()
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
          {/* Compose override warning for diff view */}
          {(() => {
            const { composeWarning } = getCurrentFileLanguageConfig()
            return composeWarning && (
              <div className="mb-3">
                <Alert
                  message={composeWarning.title}
                  description={
                    <div className="space-y-2">
                      <p>{composeWarning.message}</p>
                      <Button
                        type="link"
                        size="small"
                        className="p-0 h-auto"
                        onClick={() => navigate(`/server/${id}/compose`)}
                      >
                        {composeWarning.linkText}
                      </Button>
                    </div>
                  }
                  type={composeWarning.severity}
                  showIcon
                  closable
                />
              </div>
            )
          })()}

          <div style={{ border: '1px solid #d9d9d9', borderRadius: '6px', overflow: 'hidden', height: '600px' }}>
            {(() => {
              const { language, config } = getCurrentFileLanguageConfig()
              return (
                <div className="h-full">
                  {config?.supportsValidation && (
                    <div className="px-3 py-2 bg-gray-50 border-b text-xs text-gray-600">
                      <span className="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-blue-100 text-blue-800">
                        {config?.description} - 语法高亮已启用
                      </span>
                    </div>
                  )}
                  <MonacoDiffEditor
                    height={config?.supportsValidation ? "570px" : "600px"}
                    language={language}
                    original={originalFileContent}
                    modified={fileContent}
                    originalTitle="文件原始内容"
                    modifiedTitle="当前编辑内容"
                    theme="vs-light"
                  />
                </div>
              )
            })()}
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