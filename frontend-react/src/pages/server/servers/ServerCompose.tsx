
import React, { useState, useRef, useEffect } from 'react'
import {
  Card,
  Button,
  Alert,
  message,
  Modal
} from 'antd'
import {
  ReloadOutlined,
  ExclamationCircleOutlined,
  CloudServerOutlined,
  DiffOutlined,
  SettingOutlined,
  QuestionCircleOutlined
} from '@ant-design/icons'
import { useParams, useNavigate } from 'react-router-dom'
import { ComposeYamlEditor, MonacoDiffEditor } from '@/components/editors'
import LoadingSpinner from '@/components/layout/LoadingSpinner'
import PageHeader from '@/components/layout/PageHeader'
import DockerComposeHelpModal from '@/components/modals/DockerComposeHelpModal'
import { useServerDetailQueries } from '@/hooks/queries/page/useServerDetailQueries'
import { useServerMutations } from '@/hooks/mutations/useServerMutations'

const ServerCompose: React.FC = () => {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()

  // 使用新的数据管理系统
  const { useServerComposeData } = useServerDetailQueries(id || '')
  const { useUpdateCompose } = useServerMutations()

  // 获取服务器详情数据和compose文件
  const {
    serverInfo,
    composeContent,
    serverLoading,
    serverError,
    serverErrorMessage,
    composeQuery
  } = useServerComposeData()


  // Compose更新mutation
  const updateComposeMutation = useUpdateCompose(id || '')

  // 本地状态
  const [rawYaml, setRawYaml] = useState('')
  const [isCompareVisible, setIsCompareVisible] = useState(false)
  const [isHelpModalVisible, setIsHelpModalVisible] = useState(false)
  const [editorKey, setEditorKey] = useState(0) // 用于强制重新渲染编辑器
  const editorRef = useRef<any>(null)

  // 当 composeFile 数据加载完成时，初始化编辑器内容
  useEffect(() => {
    if (composeContent) {
      setRawYaml(composeContent)
    }
  }, [composeContent, id])


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
  if (serverError || composeQuery.isError) {
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



  // 提交并重建服务器
  const handleSubmitAndRebuild = async () => {
    try {
      // 强制重新获取最新的服务器配置，确保diff对比是准确的
      await composeQuery.refetch()
    } catch {
      message.warning('获取最新配置失败，将使用当前缓存的配置进行对比')
    }

    const hasChanges = rawYaml.trim() !== composeContent?.trim()

    Modal.confirm({
      title: '提交并重建服务器',
      content: (
        <div className="space-y-4">
          <p>确定要提交配置并重建服务器吗？这将下线当前服务器并使用新配置重新创建。</p>
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

          // 重新获取最新配置，这会触发组件重新渲染和一致性检查
          await composeQuery.refetch()

          // 强制重新渲染编辑器
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
      content: '确定要重新载入配置吗？这将丢失当前编辑器中的更改，恢复到服务器的在线配置。',
      okText: '确认',
      cancelText: '取消',
      icon: <ExclamationCircleOutlined />,
      onOk: () => {
        // 重新载入到服务器的原始配置
        const originalConfig = composeContent || ''
        setRawYaml(originalConfig)

        // 强制重新渲染编辑器
        setEditorKey(prev => prev + 1)

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
    } catch {
      message.error('获取最新配置失败，使用当前缓存的配置进行对比')
      setIsCompareVisible(true)
    }
  }

  const handleYamlChange = (value: string | undefined) => {
    if (value !== undefined) {
      setRawYaml(value)
    }
  }

  return (
    <div className="space-y-4">
      <PageHeader
        title="设置"
        icon={<SettingOutlined />}
        serverTag={serverInfo.name}
        actions={
          <>
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
              type="primary"
              danger
              icon={<CloudServerOutlined />}
              onClick={handleSubmitAndRebuild}
            >
              提交并重建
            </Button>
          </>
        }
      />

      <Card
        title={
          <div className="flex items-center justify-between w-full">
            <span>Docker Compose 配置</span>
            <Button
              size="small"
              icon={<QuestionCircleOutlined />}
              onClick={() => setIsHelpModalVisible(true)}
              type="text"
            >
              配置帮助
            </Button>
          </div>
        }
      >
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
        description="请直接编辑上方的 Docker Compose YAML 配置文件。需要点击提交并重建才能生效。"
        type="info"
        showIcon
      />

      {/* Docker Compose 帮助模态框 */}
      <DockerComposeHelpModal
        open={isHelpModalVisible}
        onCancel={() => setIsHelpModalVisible(false)}
        page="ServerCompose"
      />
    </div>
  )
}

export default ServerCompose
