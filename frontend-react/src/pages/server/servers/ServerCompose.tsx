import React, { useState, useRef, useEffect } from 'react'
import {
  Card,
  Button,
  Alert,
  App,
  Modal,
} from 'antd'
import {
  ReloadOutlined,
  ExclamationCircleOutlined,
  CloudServerOutlined,
  DiffOutlined,
  SettingOutlined,
  QuestionCircleOutlined,
  EyeOutlined,
} from '@ant-design/icons'
import { useParams, useNavigate } from 'react-router-dom'
import { ComposeYamlEditor, MonacoDiffEditor, SimpleEditor } from '@/components/editors'
import LoadingSpinner from '@/components/layout/LoadingSpinner'
import PageHeader from '@/components/layout/PageHeader'
import DockerComposeHelpModal from '@/components/modals/DockerComposeHelpModal'
import RebuildProgressModal from '@/components/modals/RebuildProgressModal'
import { useServerDetailQueries } from '@/hooks/queries/page/useServerDetailQueries'
import { useServerMutations } from '@/hooks/mutations/useServerMutations'
import { useServerTemplatePreview, useServerTemplateConfig } from '@/hooks/queries/base/useTemplateQueries'
import { useTemplateMutations } from '@/hooks/mutations/useTemplateMutations'
import RjsfForm from '@/components/forms/rjsfTheme'
import validator from '@rjsf/validator-ajv8'
import type { RJSFSchema, UiSchema } from '@rjsf/utils'

const ServerCompose: React.FC = () => {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { modal, message } = App.useApp()

  // Check if server is template-based
  const { data: templatePreview, isLoading: previewLoading } = useServerTemplatePreview(id || null)
  const isTemplateBased = templatePreview?.is_template_based ?? false

  // Template config for template-based servers
  const { data: templateConfig, isLoading: templateConfigLoading, refetch: refetchTemplateConfig } = useServerTemplateConfig(
    isTemplateBased ? id || null : null
  )

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

  // Template mutations
  const { useUpdateServerTemplateConfig, usePreviewRenderedYaml } = useTemplateMutations()
  const updateTemplateConfigMutation = useUpdateServerTemplateConfig()
  const previewMutation = usePreviewRenderedYaml()

  // 本地状态
  const [rawYaml, setRawYaml] = useState('')
  const [isCompareVisible, setIsCompareVisible] = useState(false)
  const [isHelpModalVisible, setIsHelpModalVisible] = useState(false)
  const [editorKey, setEditorKey] = useState(0)
  const editorRef = useRef<any>(null)

  // Template form state
  const [templateFormData, setTemplateFormData] = useState<Record<string, unknown>>({})
  const [previewYaml, setPreviewYaml] = useState<string | null>(null)
  const [isPreviewModalVisible, setIsPreviewModalVisible] = useState(false)

  // Rebuild task tracking state
  const [rebuildTaskId, setRebuildTaskId] = useState<string | null>(null)
  const [isRebuildModalVisible, setIsRebuildModalVisible] = useState(false)

  // UI Schema to make 'name' field read-only in edit mode
  const templateUiSchema: UiSchema = {
    name: {
      "ui:disabled": true,
      "ui:help": "服务器名称不可修改",
    },
  }

  // Initialize template form data
  useEffect(() => {
    if (templateConfig?.variable_values) {
      setTemplateFormData(templateConfig.variable_values)
    }
  }, [templateConfig])

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

  // 加载状态
  if (previewLoading || serverLoading || composeQuery.isLoading || !serverInfo) {
    return <LoadingSpinner height="16rem" tip="加载配置文件中..." />
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

  // Template form change handler
  const handleTemplateFormChange = (data: { formData?: Record<string, unknown> }) => {
    if (data.formData) {
      setTemplateFormData(data.formData)
    }
  }

  // Preview YAML for template mode
  const handlePreviewYaml = async () => {
    if (!templateConfig?.template_id || !templateFormData) return

    const yaml = await previewMutation.mutateAsync({
      id: templateConfig.template_id,
      variableValues: templateFormData,
    })
    setPreviewYaml(yaml)
    setIsPreviewModalVisible(true)
  }

  // Submit template config
  const handleSubmitTemplateConfig = async () => {
    modal.confirm({
      title: '提交并重建服务器',
      content: '确定要提交配置并重建服务器吗？这将下线当前服务器并使用新配置重新创建。',
      okText: '确认重建',
      okType: 'danger',
      cancelText: '取消',
      icon: <ExclamationCircleOutlined />,
      onOk: async () => {
        const result = await updateTemplateConfigMutation.mutateAsync({
          serverId: id!,
          variableValues: templateFormData,
        })
        setRebuildTaskId(result.task_id)
        setIsRebuildModalVisible(true)
      }
    })
  }

  // Reset template form
  const handleResetTemplateForm = () => {
    modal.confirm({
      title: '重新载入配置',
      content: '确定要重新载入配置吗？这将丢失当前表单中的更改。',
      okText: '确认',
      cancelText: '取消',
      icon: <ExclamationCircleOutlined />,
      onOk: async () => {
        await refetchTemplateConfig()
        if (templateConfig?.variable_values) {
          setTemplateFormData(templateConfig.variable_values)
        }
        message.info('配置已重新载入')
      }
    })
  }

  // 提交并重建服务器 (traditional mode)
  const handleSubmitAndRebuild = async () => {
    try {
      await composeQuery.refetch()
    } catch {
      message.warning('获取最新配置失败，将使用当前缓存的配置进行对比')
    }

    const hasChanges = rawYaml.trim() !== composeContent?.trim()

    modal.confirm({
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
          const result = await updateComposeMutation.mutateAsync(rawYaml)
          setRebuildTaskId(result.task_id)
          setIsRebuildModalVisible(true)
        } catch (error: any) {
          message.error(`配置提交失败: ${error.message}`)
        }
      }
    })
  }

  const handleReset = () => {
    modal.confirm({
      title: '重新载入配置',
      content: '确定要重新载入配置吗？这将丢失当前编辑器中的更改，恢复到服务器的在线配置。',
      okText: '确认',
      cancelText: '取消',
      icon: <ExclamationCircleOutlined />,
      onOk: () => {
        const originalConfig = composeContent || ''
        setRawYaml(originalConfig)
        setEditorKey(prev => prev + 1)
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

  // Render template-based editing
  if (isTemplateBased) {
    if (templateConfigLoading || !templateConfig) {
      return <LoadingSpinner height="16rem" tip="加载模板配置中..." />
    }

    return (
      <div className="flex flex-col h-full gap-4">
        <PageHeader
          title="设置"
          icon={<SettingOutlined />}
          serverTag={serverInfo.name}
          actions={
            <>
              <Button
                icon={<EyeOutlined />}
                onClick={handlePreviewYaml}
                loading={previewMutation.isPending}
              >
                预览 YAML
              </Button>
              <Button
                icon={<ReloadOutlined />}
                onClick={handleResetTemplateForm}
              >
                重新载入
              </Button>
              <Button
                type="primary"
                danger
                icon={<CloudServerOutlined />}
                onClick={handleSubmitTemplateConfig}
                loading={updateTemplateConfigMutation.isPending}
              >
                提交并重建
              </Button>
            </>
          }
        />

        <Alert
          message="模板模式"
          description={`此服务器使用模板 "${templateConfig.template_name}" 创建，请通过下方表单修改配置。`}
          type="info"
          showIcon
        />

        <Card
          className="flex-1"
          title="配置参数"
        >
          <RjsfForm
            schema={templateConfig.json_schema as RJSFSchema}
            uiSchema={templateUiSchema}
            formData={templateFormData}
            validator={validator}
            onChange={handleTemplateFormChange}
            showErrorList={false}
            liveValidate
          >
            <div /> {/* Hide default submit button */}
          </RjsfForm>
        </Card>

        {/* Preview YAML Modal */}
        <Modal
          title="预览生成的 YAML"
          open={isPreviewModalVisible}
          onCancel={() => setIsPreviewModalVisible(false)}
          width={1000}
          footer={[
            <Button key="close" onClick={() => setIsPreviewModalVisible(false)}>
              关闭
            </Button>
          ]}
        >
          {previewYaml && (
            <SimpleEditor
              value={previewYaml}
              language="yaml"
              height="60vh"
              options={{ readOnly: true }}
            />
          )}
        </Modal>

        {/* Rebuild Progress Modal */}
        <RebuildProgressModal
          open={isRebuildModalVisible}
          taskId={rebuildTaskId}
          serverId={id}
          onClose={() => {
            setIsRebuildModalVisible(false)
            setRebuildTaskId(null)
          }}
          onComplete={() => {
            setIsRebuildModalVisible(false)
            setRebuildTaskId(null)
            refetchTemplateConfig()
            composeQuery.refetch()
          }}
        />
      </div>
    )
  }

  // Render traditional YAML editing
  return (
    <div className="flex flex-col h-full gap-4">
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
        className="flex-1 min-h-0 flex flex-col"
        classNames={{ body: "flex flex-col flex-1 min-h-0 !p-0" }}
        title={
          <div className="flex items-center justify-between w-full">
            <div className="flex items-center gap-3">
              <span>Docker Compose 配置</span>
              <span className="text-xs text-gray-400 font-normal">此处的修改在点击提交并重建后才会生效，退出该页面将丢失未保存的更改。</span>
            </div>
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
          className="h-full"
          height="100%"
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

      {/* Docker Compose 帮助模态框 */}
      <DockerComposeHelpModal
        open={isHelpModalVisible}
        onCancel={() => setIsHelpModalVisible(false)}
        page="ServerCompose"
      />

      {/* Rebuild Progress Modal */}
      <RebuildProgressModal
        open={isRebuildModalVisible}
        taskId={rebuildTaskId}
        serverId={id}
        onClose={() => {
          setIsRebuildModalVisible(false)
          setRebuildTaskId(null)
        }}
        onComplete={() => {
          setIsRebuildModalVisible(false)
          setRebuildTaskId(null)
          composeQuery.refetch()
          setEditorKey(prev => prev + 1)
        }}
      />
    </div>
  )
}

export default ServerCompose
