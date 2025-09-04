
import React, { useState, useRef, useEffect, useMemo } from 'react'
import {
  Card,
  Button,
  Space,
  Typography,
  Alert,
  message,
  Modal
} from 'antd'
import {
  SaveOutlined,
  ReloadOutlined,
  ExclamationCircleOutlined,
  CloudServerOutlined,
  DiffOutlined
} from '@ant-design/icons'
import { useParams, useNavigate } from 'react-router-dom'
import { ComposeYamlEditor, MonacoDiffEditor } from '@/components/editors'
import LoadingSpinner from '@/components/layout/LoadingSpinner'
import ServerStateTag from '@/components/overview/ServerStateTag'
import { useServerDetailQueries } from '@/hooks/queries/useServerDetailQueries'
import { useServerMutations } from '@/hooks/mutations/useServerMutations'

const { Title } = Typography

const ServerCompose: React.FC = () => {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()

  // 使用新的数据管理系统
  const { useServerComposeData, useServerDetailData } = useServerDetailQueries(id || '')
  const { useUpdateCompose } = useServerMutations()

  // 获取服务器详情数据和compose文件
  const {
    serverInfo,
    composeContent,
    serverLoading,
    serverError,
    serverErrorMessage,
    hasServerInfo,
    composeQuery
  } = useServerComposeData()

  // 获取服务器状态数据
  const { status } = useServerDetailData()

  // Compose更新mutation
  const updateComposeMutation = useUpdateCompose(id || '')

  // 本地状态
  const [rawYaml, setRawYaml] = useState('')
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false)
  const [isCompareVisible, setIsCompareVisible] = useState(false)
  const [editorKey, setEditorKey] = useState(0) // 用于强制重新渲染编辑器
  const [checkTrigger, setCheckTrigger] = useState(0) // 用于触发一致性检查
  const editorRef = useRef<any>(null)

  // 当 composeFile 数据加载完成时，初始化编辑器内容
  useEffect(() => {
    if (composeContent) {
      const savedConfig = localStorage.getItem(`compose-${id}`)
      setRawYaml(savedConfig || composeContent)
    }
  }, [composeContent, id])

  // 定期检查配置一致性，确保状态及时更新
  useEffect(() => {
    if (!composeContent) return

    const checkInterval = setInterval(() => {
      // 触发一致性检查更新
      setCheckTrigger(prev => prev + 1)
    }, 3000) // 每3秒检查一次

    return () => clearInterval(checkInterval)
  }, [composeContent, id])

  // 实时检查浏览器存储和服务器配置的一致性
  const checkConfigConsistency = () => {
    const currentSavedConfig = localStorage.getItem(`compose-${id}`)
    const serverConfig = composeContent

    if (!currentSavedConfig || !serverConfig) {
      return { hasSavedConfig: false, hasOnlineChanges: false }
    }

    const hasSavedConfig = !!currentSavedConfig
    const hasOnlineChanges = hasSavedConfig && currentSavedConfig.trim() !== serverConfig.trim()

    return { hasSavedConfig, hasOnlineChanges }
  }

  // 使用useMemo来优化一致性检查，依赖于checkTrigger和composeContent
  const { hasSavedConfig, hasOnlineChanges } = useMemo(() => {
    return checkConfigConsistency()
  }, [checkTrigger, composeContent, id])

  // 如果没有服务器ID，返回错误
  if (!id) {
    return (
      <div className="flex justify-center items-center min-h-64">
        <Alert
          message="参数错误"
          description="缺少服务器ID参数"
          type="error"
          action={
            <Button size="small" onClick={() => navigate('/overview')}>
              返回概览
            </Button>
          }
        />
      </div>
    )
  }

  // 错误状态
  if (serverError || composeQuery.isError || !hasServerInfo) {
    const errorMessage = (serverErrorMessage as any)?.message || `无法加载服务器 "${id}" 的配置信息`
    return (
      <div className="flex justify-center items-center min-h-64">
        <Alert
          message="加载失败"
          description={errorMessage}
          type="error"
          action={
            <Button size="small" onClick={() => navigate('/overview')}>
              返回概览
            </Button>
          }
        />
      </div>
    )
  }

  // 加载状态
  if (serverLoading || composeQuery.isLoading || !serverInfo || !composeContent) {
    return <LoadingSpinner height="16rem" tip="加载配置文件中..." />
  }

  // 只有当有本地配置且与在线配置不同时才显示未保存更改
  const showUnsavedChanges = hasUnsavedChanges && hasSavedConfig

  // 保存到浏览器本地存储
  const handleSaveLocal = () => {
    try {
      localStorage.setItem(`compose-${id}`, rawYaml)
      message.success('配置已保存到浏览器本地')
      setHasUnsavedChanges(false)

      // 立即触发一致性检查
      setCheckTrigger(prev => prev + 1)
    } catch (error) {
      message.error('保存到浏览器失败')
    }
  }

  // 提交并重建服务器
  const handleSubmitAndRebuild = async () => {
    try {
      // 强制重新获取最新的服务器配置，确保diff对比是准确的
      await composeQuery.refetch()
    } catch (error) {
      message.warning('获取最新配置失败，将使用当前缓存的配置进行对比')
    }
    
    const hasChanges = rawYaml.trim() !== composeContent?.trim()
    
    Modal.confirm({
      title: '提交并重建服务器',
      content: (
        <div className="space-y-4">
          <p>确定要提交配置并重建服务器吗？这将停止当前服务器并使用新配置重新创建。</p>
          {hasChanges && (
            <div>
              <div className="mb-2">
                <strong>配置差异预览：</strong>
              </div>
              <div style={{ 
                border: '1px solid #d9d9d9', 
                borderRadius: '6px', 
                overflow: 'hidden', 
                height: '600px',
                backgroundColor: '#fafafa'
              }}>
                <MonacoDiffEditor
                  height="600px"
                  language="yaml"
                  original={composeContent || ''}
                  modified={rawYaml}
                  theme="vs-light"
                  options={{
                    minimap: { enabled: false },
                    scrollBeyondLastLine: false,
                    fontSize: 12,
                    lineNumbers: 'off',
                    folding: false,
                    wordWrap: 'on',
                    scrollbar: {
                      vertical: 'visible',
                      horizontal: 'visible'
                    }
                  }}
                />
              </div>
            </div>
          )}
          {!hasChanges && (
            <Alert
              message="没有检测到配置更改"
              description="当前编辑的配置与服务器配置相同，重建后不会有任何变化。"
              type="info"
              showIcon
              className="mt-2"
            />
          )}
        </div>
      ),
      width: 800,
      okText: '确认重建',
      okType: 'danger',
      cancelText: '取消',
      icon: <ExclamationCircleOutlined />,
      onOk: async () => {
        try {
          // 调用 API 提交配置并重建服务器
          await updateComposeMutation.mutateAsync(rawYaml)
          message.info('服务器重建需要几分钟时间，请稍候')
          setHasUnsavedChanges(false)

          // 清除浏览器存储
          localStorage.removeItem(`compose-${id}`)

          // 重新获取最新配置，这会触发组件重新渲染和一致性检查
          await composeQuery.refetch()

          // 强制触发一致性检查
          setCheckTrigger(prev => prev + 1)
          setEditorKey(prev => prev + 1)

        } catch (error: any) {
          message.error(`配置提交失败: ${error.message}`)
        }
      }
    })
  }

  const handleReset = () => {
    Modal.confirm({
      title: '重新载入配置',
      content: '确定要重新载入配置吗？这将丢失所有未保存的更改，恢复到服务器的在线配置。',
      okText: '确认',
      cancelText: '取消',
      icon: <ExclamationCircleOutlined />,
      onOk: () => {
        // 重新载入应该恢复到服务器的原始配置，而不是本地存储的配置
        const originalConfig = composeContent || ''
        setRawYaml(originalConfig)
        setHasUnsavedChanges(false)

        // 同时清除本地存储的配置
        localStorage.removeItem(`compose-${id}`)

        // 强制重新渲染编辑器和触发一致性检查
        setEditorKey(prev => prev + 1)
        setCheckTrigger(prev => prev + 1)

        // 延迟更新编辑器内容，确保重新渲染完成
        setTimeout(() => {
          if (editorRef.current) {
            editorRef.current.setValue(originalConfig)
          }
        }, 100)

        message.info('配置已重新载入到服务器在线状态')
      }
    })
  }

  const handleCompare = async () => {
    try {
      // 强制重新获取最新的服务器配置
      await composeQuery.refetch()
      setIsCompareVisible(true)
    } catch (error) {
      message.error('获取最新配置失败，使用当前缓存的配置进行对比')
      setIsCompareVisible(true)
    }
  }

  const handleYamlChange = (value: string | undefined) => {
    if (value !== undefined) {
      setRawYaml(value)
      // 只有当有本地配置或者当前值与在线数据不同时才标记为未保存
      const currentSavedConfig = localStorage.getItem(`compose-${id}`)
      const hasLocalConfig = !!currentSavedConfig
      const isDifferentFromOnline = value.trim() !== composeQuery.data?.trim()

      setHasUnsavedChanges(hasLocalConfig || isDifferentFromOnline)
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <div className="flex items-center gap-3">
          <Title level={2} className="!mb-0 !mt-0">{serverInfo.name} - 设置</Title>
          {status && <ServerStateTag state={status} />}
        </div>
        <Space>
          {showUnsavedChanges && (
            <Alert
              message="有未保存的更改"
              type="warning"
              showIcon
              className="mb-0"
            />
          )}
          {hasOnlineChanges && (
            <Alert
              message="本地配置与服务器配置不一致"
              type="info"
              showIcon
              className="mb-0"
              action={
                <Button
                  size="small"
                  type="link"
                  onClick={handleCompare}
                >
                  查看差异
                </Button>
              }
            />
          )}
          <Button
            icon={<DiffOutlined />}
            onClick={handleCompare}
          >
            差异对比
          </Button>
          <Button
            icon={<ReloadOutlined />}
            onClick={handleReset}
          >
            重新载入
          </Button>
          <Button
            icon={<SaveOutlined />}
            onClick={handleSaveLocal}
          >
            保存到本地
          </Button>
          <Button
            type="primary"
            danger
            icon={<CloudServerOutlined />}
            onClick={handleSubmitAndRebuild}
          >
            提交并重建
          </Button>
        </Space>
      </div>

      <Card title="Docker Compose 配置">
        <ComposeYamlEditor
          key={editorKey}
          height="600px"
          value={rawYaml}
          onChange={handleYamlChange}
          onMount={(editor: any) => {
            editorRef.current = editor
          }}
          theme="vs-light"
          path="docker-compose.yml"
        />
      </Card>

      {/* 对比窗口 */}
      <Modal
        title="配置差异对比"
        open={isCompareVisible}
        onCancel={() => setIsCompareVisible(false)}
        width={1400}
        footer={[
          <Button key="close" onClick={() => setIsCompareVisible(false)}>
            关闭
          </Button>
        ]}
      >
        <div className="space-y-4">
          <Alert
            message="差异对比视图"
            description="左侧为服务器当前配置，右侧为本地编辑的配置。高亮显示的是差异部分。"
            type="info"
            showIcon
          />
          <div style={{ border: '1px solid #d9d9d9', borderRadius: '6px', overflow: 'hidden', height: '600px' }}>
            <MonacoDiffEditor
              key={`${composeContent?.length || 0}-${rawYaml.length}`}
              height="600px"
              language="yaml"
              original={composeContent || ''}
              modified={rawYaml}
              originalTitle="服务器当前配置"
              modifiedTitle="本地编辑配置"
              theme="vs-light"
              onMount={(editor: any) => {
                console.log('Diff editor mounted', editor)
              }}
            />
          </div>
        </div>
      </Modal>

      {/* 编辑说明 */}
      <Alert
        message="编辑说明"
        description="请直接编辑上方的 Docker Compose YAML 配置文件。保存后需要重建服务器才能生效。"
        type="info"
        showIcon
      />
    </div>
  )
}

export default ServerCompose
