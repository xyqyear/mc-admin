import React, { useState, useMemo } from 'react'
import {
  Modal,
  Button,
  Progress,
  Radio,
  Space,
  Alert,
  Divider,
  Typography,
  Card,
  Statistic,
  Row,
  Col,
  Tag,
  App
} from 'antd'
import {
  WarningOutlined,
  CheckCircleOutlined
} from '@ant-design/icons'
import type {
  OverwriteConflict,
  OverwritePolicy,
  FileStructureItem
} from '@/hooks/api/fileApi'
import { useFileMutations } from '@/hooks/mutations/useFileMutations'
import FileUploadTree from './FileUploadTree'
import ConflictTree from './ConflictTree'

const { Text, Title } = Typography

interface MultiFileUploadModalProps {
  open: boolean
  onCancel: () => void
  onComplete: () => void
  serverId: string
  basePath: string
  initialFiles?: File[]
}

interface UploadStep {
  step: 'select' | 'conflicts' | 'uploading' | 'complete'
  files: File[]
  conflicts: OverwriteConflict[]
  sessionId?: string
  overwritePolicy?: OverwritePolicy
  uploadProgress?: {
    totalProgress: number
    uploadedFiles: number
    totalFiles: number
    totalSize: number
    uploadedSize: number
  }
  results?: Record<string, { status: string; reason?: string }>
  error?: string
}

const MultiFileUploadModal: React.FC<MultiFileUploadModalProps> = ({
  open,
  onCancel,
  onComplete,
  serverId,
  basePath,
  initialFiles = []
}) => {
  const { message } = App.useApp()
  const {
    useCheckUploadConflicts,
    useSetUploadPolicy,
    useUploadMultipleFiles
  } = useFileMutations(serverId)

  const checkConflictsMutation = useCheckUploadConflicts()
  const setUploadPolicyMutation = useSetUploadPolicy()
  const uploadMultipleFilesMutation = useUploadMultipleFiles()

  const [uploadState, setUploadState] = useState<UploadStep>({
    step: 'select',
    files: [],
    conflicts: []
  })

  const [conflictDecisions, setConflictDecisions] = useState<Record<string, boolean>>({})
  const [uploadAbortController, setUploadAbortController] = useState<AbortController | null>(null)

  // 重置状态函数
  const resetState = () => {
    setUploadState({
      step: 'select',
      files: [],
      conflicts: [],
      sessionId: undefined,
      overwritePolicy: undefined,
      uploadProgress: undefined,
      results: undefined,
      error: undefined
    })
    setConflictDecisions({})
    setUploadAbortController(null)
  }

  // Initialize files when modal opens
  React.useEffect(() => {
    if (open && initialFiles.length > 0) {
      // 完全重置状态，然后设置新文件
      resetState()
      setUploadState({
        step: 'select',
        files: initialFiles,
        conflicts: [],
        sessionId: undefined,
        overwritePolicy: undefined,
        uploadProgress: undefined,
        results: undefined,
        error: undefined
      })
    } else if (open) {
      // 完全重置状态
      resetState()
    } else if (!open) {
      // 模态框关闭时也重置状态
      resetState()
    }
  }, [open, initialFiles])


  // 构建文件结构
  const buildFileStructure = (files: File[]): FileStructureItem[] => {
    const structure: FileStructureItem[] = []
    const directories = new Set<string>()

    files.forEach(file => {
      const relativePath = (file as any).webkitRelativePath || file.name

      // 处理目录路径
      const pathParts = relativePath.split('/')
      let currentPath = ''

      // 添加目录结构
      for (let i = 0; i < pathParts.length - 1; i++) {
        currentPath += (currentPath ? '/' : '') + pathParts[i]
        if (!directories.has(currentPath)) {
          directories.add(currentPath)
          structure.push({
            path: currentPath,
            name: pathParts[i],
            type: 'directory'
          })
        }
      }

      // 添加文件
      structure.push({
        path: relativePath,
        name: file.name,
        type: 'file',
        size: file.size
      })
    })

    return structure
  }

  // 计算总大小
  const totalSize = useMemo(() => {
    return uploadState.files.reduce((total, file) => {
      return total + file.size
    }, 0)
  }, [uploadState.files])

  // 格式化文件大小
  const formatFileSize = (bytes: number) => {
    if (bytes === 0) return '0 B'
    const k = 1024
    const sizes = ['B', 'KB', 'MB', 'GB']
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i]
  }

  // 检查冲突
  const handleCheckConflicts = async () => {
    const fileStructure = buildFileStructure(uploadState.files)

    try {
      const response = await checkConflictsMutation.mutateAsync({
        path: basePath,
        uploadRequest: {
          files: fileStructure
        }
      })

      setUploadState(prev => ({
        ...prev,
        step: response.conflicts.length > 0 ? 'conflicts' : 'uploading',
        conflicts: response.conflicts,
        sessionId: response.session_id
      }))

      // 如果有冲突，默认全部选中（覆盖）
      if (response.conflicts.length > 0) {
        const defaultDecisions: Record<string, boolean> = {}
        response.conflicts.forEach(conflict => {
          defaultDecisions[conflict.path] = true // 默认全部覆盖
        })
        setConflictDecisions(defaultDecisions)
      }

      // 如果没有冲突，直接开始上传
      if (response.conflicts.length === 0) {
        await handleStartUpload(response.session_id, { mode: 'always_overwrite' })
      }
    } catch (error: any) {
      message.error('检查冲突失败')
      console.error('Check conflicts error:', error)
    }
  }

  // 处理覆盖策略
  const handleOverwritePolicy = (policy: OverwritePolicy) => {
    setUploadState(prev => ({
      ...prev,
      overwritePolicy: policy
    }))
  }


  // 开始上传
  const handleStartUpload = async (sessionId?: string, policy?: OverwritePolicy) => {
    const currentSessionId = sessionId || uploadState.sessionId
    const currentPolicy = policy || uploadState.overwritePolicy

    if (!currentSessionId || !currentPolicy) {
      message.error('缺少上传会话或策略')
      return
    }

    setUploadState(prev => ({
      ...prev,
      step: 'uploading',
      uploadProgress: {
        totalProgress: 0,
        uploadedFiles: 0,
        totalFiles: prev.files.length,
        totalSize,
        uploadedSize: 0
      }
    }))

    try {
      // 检查是否需要分块上传（超过1000个文件）
      const needsChunking = uploadState.files.length > 1000

      // 创建AbortController用于取消上传
      const abortController = new AbortController()
      setUploadAbortController(abortController)

      // 设置覆盖策略，如果需要分块则设置为可重用
      // 策略设置一次性处理所有文件，无需分块
      await setUploadPolicyMutation.mutateAsync({
        sessionId: currentSessionId,
        policy: currentPolicy,
        reusable: needsChunking
      })

      // 开始上传 - 这里会自动处理分块逻辑
      const result = await uploadMultipleFilesMutation.mutateAsync({
        sessionId: currentSessionId,
        path: basePath,
        files: uploadState.files,
        abortSignal: abortController.signal,
        onProgress: (progress) => {
          setUploadState(prev => ({
            ...prev,
            uploadProgress: {
              ...prev.uploadProgress!,
              totalProgress: progress.percent,
              uploadedSize: progress.loaded
            }
          }))
        }
      })

      setUploadState(prev => ({
        ...prev,
        step: 'complete',
        results: result.results
      }))

    } catch (error: any) {
      // 检查是否为用户取消操作
      if (error.name === 'AbortError' || error.code === 'ERR_CANCELED') {
        message.info('上传已取消')
        setUploadState(prev => ({
          ...prev,
          step: 'select',
          error: '上传已取消'
        }))
      } else {
        message.error('上传失败')
        setUploadState(prev => ({
          ...prev,
          step: 'select',
          error: error.message || '上传失败'
        }))
      }
    } finally {
      setUploadAbortController(null)
    }
  }

  // 取消上传
  const handleCancelUpload = () => {
    if (uploadAbortController) {
      uploadAbortController.abort()
      message.info('正在取消上传...')
    }
  }

  // Handle upload completion callback
  const handleUploadSuccess = () => {
    onComplete()
    // Reset state
    setUploadState({
      step: 'select',
      files: [],
      conflicts: []
    })
    setConflictDecisions({})
  }

  // 重置状态
  const handleReset = () => {
    resetState()
  }

  // 处理冲突树的选择
  const handleConflictTreeCheck = (checked: React.Key[] | { checked: React.Key[]; halfChecked: React.Key[] }) => {
    const checkedKeys = Array.isArray(checked) ? checked : checked.checked
    const newDecisions: Record<string, boolean> = {}

    // 只处理冲突文件的选择状态
    uploadState.conflicts.forEach(conflict => {
      newDecisions[conflict.path] = checkedKeys.includes(conflict.path)
    })

    setConflictDecisions(newDecisions)

    // 更新覆盖策略
    if (uploadState.overwritePolicy?.mode === 'per_file') {
      handleOverwritePolicy({
        mode: 'per_file',
        decisions: uploadState.conflicts.map(c => ({
          path: c.path,
          overwrite: newDecisions[c.path] ?? false
        }))
      })
    }
  }

  // 获取冲突树的选中keys
  const getConflictCheckedKeys = (): React.Key[] => {
    return uploadState.conflicts
      .filter(conflict => conflictDecisions[conflict.path] ?? true) // 默认全选
      .map(conflict => conflict.path)
  }

  // 渲染不同步骤的内容
  const renderContent = () => {
    switch (uploadState.step) {
      case 'select':
        return (
          <div className="space-y-4">
            {uploadState.files.length > 0 ? (
              <>
                <Card size="small">
                  <Row gutter={16}>
                    <Col span={8}>
                      <Statistic title="文件数量" value={uploadState.files.length} />
                    </Col>
                    <Col span={8}>
                      <Statistic title="总大小" value={formatFileSize(totalSize)} />
                    </Col>
                    <Col span={8}>
                      <Statistic title="目标路径" value={basePath} />
                    </Col>
                  </Row>
                </Card>

                <FileUploadTree files={uploadState.files} />
              </>
            ) : (
              <Alert
                message="未选择文件"
                description="请关闭该窗口并使用拖拽的方式选择要上传的文件或文件夹"
                type="info"
                showIcon
              />
            )}
          </div>
        )

      case 'conflicts':
        return (
          <div className="space-y-4">
            <Alert
              message="检测到文件冲突"
              description={`有 ${uploadState.conflicts.length} 个文件将会覆盖现有文件，请选择处理方式`}
              type="warning"
              icon={<WarningOutlined />}
              showIcon
            />

            <div>
              <Title level={5}>覆盖策略</Title>
              <Radio.Group
                value={uploadState.overwritePolicy?.mode}
                onChange={(e) => {
                  const mode = e.target.value
                  handleOverwritePolicy({
                    mode,
                    decisions: mode === 'per_file' ?
                      uploadState.conflicts.map(c => ({
                        path: c.path,
                        overwrite: conflictDecisions[c.path] ?? false
                      })) : undefined
                  })
                }}
              >
                <Space orientation="vertical">
                  <Radio value="always_overwrite">总是覆盖所有冲突文件</Radio>
                  <Radio value="never_overwrite">跳过所有冲突文件</Radio>
                  <Radio value="per_file">为每个文件单独选择</Radio>
                </Space>
              </Radio.Group>
            </div>

            {uploadState.overwritePolicy?.mode === 'per_file' && (
              <>
                <Divider />
                <ConflictTree
                  conflicts={uploadState.conflicts}
                  checkedKeys={getConflictCheckedKeys()}
                  onCheck={handleConflictTreeCheck}
                />
              </>
            )}
          </div>
        )

      case 'uploading':
        return (
          <div className="space-y-4">
            <div className="text-center">
              <Title level={4}>正在上传文件...</Title>
              {uploadState.files.length > 1000 && (
                <Text type="secondary" className="block mb-2">
                  分块上传模式 - 每批次最多1000个文件
                </Text>
              )}
              <Progress
                percent={uploadState.uploadProgress?.totalProgress || 0}
                status="active"
                format={(percent) => `${percent}% (${uploadState.uploadProgress?.uploadedFiles}/${uploadState.uploadProgress?.totalFiles})`}
              />
            </div>


            <Card size="small">
              <Row gutter={16}>
                <Col span={12}>
                  <Statistic
                    title="已上传"
                    value={`${uploadState.uploadProgress?.uploadedFiles || 0}/${uploadState.uploadProgress?.totalFiles || 0}`}
                  />
                </Col>
                <Col span={12}>
                  <Statistic
                    title="传输大小"
                    value={formatFileSize(uploadState.uploadProgress?.uploadedSize || 0)}
                    suffix={`/ ${formatFileSize(uploadState.uploadProgress?.totalSize || 0)}`}
                  />
                </Col>
              </Row>
            </Card>
          </div>
        )

      case 'complete':
        return (
          <div className="space-y-4">
            <div className="text-center">
              <CheckCircleOutlined style={{ fontSize: 48, color: '#52c41a' }} />
              <Title level={4} style={{ color: '#52c41a' }}>上传完成！</Title>
            </div>

            <Card title="上传结果">
              <div style={{ maxHeight: '300px', overflowY: 'auto' }}>
                {uploadState.results && Object.entries(uploadState.results).map(([filepath, result]) => (
                  <div key={filepath} className="flex justify-between items-center py-1">
                    <Text>{filepath}</Text>
                    <Tag color={
                      result.status === 'success' ? 'success' :
                        result.status === 'failed' ? 'error' : 'warning'
                    }>
                      {result.status === 'success' ? '成功' :
                        result.status === 'failed' ? '失败' : '跳过'}
                      {result.reason && ` (${result.reason})`}
                    </Tag>
                  </div>
                ))}
              </div>
            </Card>
          </div>
        )

      default:
        return null
    }
  }

  // 渲染底部按钮
  const renderFooter = () => {
    switch (uploadState.step) {
      case 'select':
        return [
          <Button key="cancel" onClick={onCancel}>
            取消
          </Button>,
          <Button
            key="check"
            type="primary"
            disabled={uploadState.files.length === 0}
            onClick={handleCheckConflicts}
          >
            检查冲突并上传
          </Button>
        ]

      case 'conflicts':
        return [
          <Button key="back" onClick={() => setUploadState(prev => ({ ...prev, step: 'select' }))}>
            返回
          </Button>,
          <Button
            key="upload"
            type="primary"
            disabled={!uploadState.overwritePolicy}
            onClick={() => handleStartUpload()}
          >
            开始上传
          </Button>
        ]

      case 'uploading':
        return [
          <Button key="cancel" onClick={handleCancelUpload} danger>
            取消上传
          </Button>
        ]

      case 'complete':
        return [
          <Button key="close" onClick={() => {
            handleReset()
            onCancel()
            handleUploadSuccess()
          }}>
            关闭
          </Button>
        ]

      default:
        return []
    }
  }

  // 处理模态框关闭
  const handleModalCancel = () => {
    // 如果正在上传，先取消上传
    if (uploadState.step === 'uploading' && uploadAbortController) {
      handleCancelUpload()
    }
    // 关闭模态框
    onCancel()
  }

  return (
    <Modal
      title="上传文件和文件夹"
      open={open}
      onCancel={handleModalCancel}
      footer={renderFooter()}
      width={800}
      maskClosable={true}
      closable={true}
    >
      {renderContent()}
    </Modal>
  )
}

export default MultiFileUploadModal