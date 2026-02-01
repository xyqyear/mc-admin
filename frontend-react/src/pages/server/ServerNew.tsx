import React, { useState, useRef, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Card,
  Form,
  Input,
  Button,
  Typography,
  Alert,
  Space,
  Switch,
  message,
  Divider,
  Tabs,
  Select,
  Empty,
} from 'antd'
import {
  FileZipOutlined,
  PlayCircleOutlined,
  PlusOutlined,
  CopyOutlined,
  QuestionCircleOutlined,
  SnippetsOutlined,
  CodeOutlined,
  EyeOutlined,
} from '@ant-design/icons'
import { ComposeYamlEditor, SimpleEditor } from '@/components/editors'
import PageHeader from '@/components/layout/PageHeader'
import ArchiveSelectionModal from '@/components/modals/ArchiveSelectionModal'
import PopulateProgressModal from '@/components/modals/PopulateProgressModal'
import ServerTemplateModal from '@/components/modals/ServerTemplateModal'
import DockerComposeHelpModal from '@/components/modals/DockerComposeHelpModal'
import { useServerMutations } from '@/hooks/mutations/useServerMutations'
import { useAutoUpdateDNS } from '@/hooks/mutations/useDnsMutations'
import { useTemplates, useTemplateSchema, useAvailablePorts } from '@/hooks/queries/base/useTemplateQueries'
import { useTemplateMutations } from '@/hooks/mutations/useTemplateMutations'
import RjsfForm from '@/components/forms/rjsfTheme'
import validator from '@rjsf/validator-ajv8'
import type { RJSFSchema } from '@rjsf/utils'

const { Text } = Typography

type CreationMode = 'traditional' | 'template'

const ServerNew: React.FC = () => {
  const navigate = useNavigate()
  const [form] = Form.useForm()
  const [composeContent, setComposeContent] = useState('')

  // Creation mode state
  const [creationMode, setCreationMode] = useState<CreationMode>('template')

  // Template mode state
  const [selectedTemplateId, setSelectedTemplateId] = useState<number | null>(null)
  const [templateFormData, setTemplateFormData] = useState<Record<string, unknown>>({})
  const [previewYaml, setPreviewYaml] = useState<string | null>(null)
  const [isPreviewModalVisible, setIsPreviewModalVisible] = useState(false)

  // Archive selection state
  const [isArchiveModalVisible, setIsArchiveModalVisible] = useState(false)
  const [selectedArchiveFile, setSelectedArchiveFile] = useState<string | null>(null)

  // Template selection state (for traditional mode - copy from existing server)
  const [isTemplateModalVisible, setIsTemplateModalVisible] = useState(false)

  // Help modal state
  const [isHelpModalVisible, setIsHelpModalVisible] = useState(false)

  // Populate progress state
  const [populateTaskId, setPopulateTaskId] = useState<string | null>(null)
  const [isPopulateProgressModalVisible, setIsPopulateProgressModalVisible] = useState(false)
  const [createdServerId, setCreatedServerId] = useState<string | null>(null)

  // Restart schedule state
  const [enableRestartSchedule, setEnableRestartSchedule] = useState(true)

  // Queries
  const { data: templates = [], isLoading: templatesLoading } = useTemplates()
  const { data: templateSchema, isLoading: schemaLoading } = useTemplateSchema(selectedTemplateId)
  const { data: availablePorts } = useAvailablePorts(creationMode === 'template')

  // Mutations
  const { useCreateServer, usePopulateServer, useCreateOrUpdateRestartSchedule } = useServerMutations()
  const createServerMutation = useCreateServer()
  const populateServerMutation = usePopulateServer()
  const createRestartScheduleMutation = useCreateOrUpdateRestartSchedule()
  const autoUpdateDNS = useAutoUpdateDNS()
  const { usePreviewRenderedYaml } = useTemplateMutations()
  const previewMutation = usePreviewRenderedYaml()

  // Initialize template form data with defaults when schema loads
  useEffect(() => {
    if (templateSchema?.json_schema) {
      const schema = templateSchema.json_schema as RJSFSchema
      const defaults: Record<string, unknown> = {}

      if (schema.properties) {
        Object.entries(schema.properties).forEach(([key, prop]) => {
          if (typeof prop === 'object' && 'default' in prop) {
            defaults[key] = prop.default
          }
        })
      }

      // Override with available ports
      if (availablePorts) {
        defaults.game_port = availablePorts.suggested_game_port
        defaults.rcon_port = availablePorts.suggested_rcon_port
      }

      setTemplateFormData(defaults)
    }
  }, [templateSchema, availablePorts])

  const handleArchiveSelect = (filename: string) => {
    setSelectedArchiveFile(filename)
    setIsArchiveModalVisible(false)
    message.success(`已选择压缩包: ${filename}`)
  }

  const handleRemoveArchive = () => {
    setSelectedArchiveFile(null)
    message.info('已移除压缩包选择')
  }

  const handleTemplateSelect = (templateContent: string) => {
    setComposeContent(templateContent)
    setIsTemplateModalVisible(false)
    form.setFieldsValue({ composeContent: templateContent })
    message.success('已应用服务器模板配置')
  }

  const handleTemplateFormChange = (data: { formData?: Record<string, unknown> }) => {
    if (data.formData) {
      setTemplateFormData(data.formData)
    }
  }

  const handlePreviewYaml = async () => {
    if (!selectedTemplateId || !templateFormData) return

    const yaml = await previewMutation.mutateAsync({
      id: selectedTemplateId,
      variableValues: templateFormData,
    })
    setPreviewYaml(yaml)
    setIsPreviewModalVisible(true)
  }

  const handleCreate = async () => {
    try {
      if (creationMode === 'template') {
        // Template mode
        if (!selectedTemplateId) {
          message.error('请选择一个模板')
          return
        }

        const serverName = templateFormData.name as string
        if (!serverName) {
          message.error('请填写服务器名称')
          return
        }

        // Create server with template
        await createServerMutation.mutateAsync({
          serverId: serverName,
          templateId: selectedTemplateId,
          variableValues: templateFormData,
        })

        // Create restart schedule if enabled
        if (enableRestartSchedule) {
          try {
            await createRestartScheduleMutation.mutateAsync({
              serverId: serverName,
            })
          } catch {
            // Restart schedule creation failed, but don't block the flow
          }
        }

        // Handle archive population
        if (selectedArchiveFile) {
          try {
            const result = await populateServerMutation.mutateAsync({
              serverId: serverName,
              archiveFilename: selectedArchiveFile,
            })
            setCreatedServerId(serverName)
            setPopulateTaskId(result.task_id)
            setIsPopulateProgressModalVisible(true)
          } catch (populateError: any) {
            message.warning(`服务器 "${serverName}" 创建成功，但数据填充失败: ${populateError.message || '未知错误'}`)
            await triggerDNSUpdateAndNavigate()
          }
        } else {
          await triggerDNSUpdateAndNavigate()
        }
      } else {
        // Traditional mode
        const values = await form.validateFields()

        await createServerMutation.mutateAsync({
          serverId: values.serverName,
          yamlContent: composeContent,
        })

        if (enableRestartSchedule) {
          try {
            await createRestartScheduleMutation.mutateAsync({
              serverId: values.serverName,
            })
          } catch {
            // Restart schedule creation failed, but don't block the flow
          }
        }

        if (selectedArchiveFile) {
          try {
            const result = await populateServerMutation.mutateAsync({
              serverId: values.serverName,
              archiveFilename: selectedArchiveFile,
            })
            setCreatedServerId(values.serverName)
            setPopulateTaskId(result.task_id)
            setIsPopulateProgressModalVisible(true)
          } catch (populateError: any) {
            message.warning(`服务器 "${values.serverName}" 创建成功，但数据填充失败: ${populateError.message || '未知错误'}`)
            await triggerDNSUpdateAndNavigate()
          }
        } else {
          await triggerDNSUpdateAndNavigate()
        }
      }
    } catch (error: any) {
      console.error('创建服务器过程中出错:', error)
    }
  }

  const triggerDNSUpdateAndNavigate = async () => {
    try {
      await autoUpdateDNS.mutateAsync()
    } catch (dnsError: any) {
      console.warn('DNS自动更新失败:', dnsError)
    }
    navigate('/overview')
  }

  const handlePopulateComplete = async () => {
    setIsPopulateProgressModalVisible(false)
    setPopulateTaskId(null)
    message.success(`服务器 "${createdServerId}" 创建并填充完成!`)
    await triggerDNSUpdateAndNavigate()
  }

  const handlePopulateClose = () => {
    setIsPopulateProgressModalVisible(false)
    setPopulateTaskId(null)
    navigate('/overview')
  }

  const handleComposeContentChange = (value: string | undefined) => {
    if (value !== undefined) {
      setComposeContent(value)
      form.setFieldsValue({ composeContent: value })
    }
  }

  useEffect(() => {
    form.setFieldsValue({ composeContent: composeContent })
  }, [form, composeContent])

  const editorRef = useRef<any>(null)

  const isLoading = createServerMutation.isPending || populateServerMutation.isPending || createRestartScheduleMutation.isPending

  return (
    <div className="space-y-4">
      <PageHeader
        title="新建服务器"
        icon={<PlusOutlined />}
      />

      <Alert
        message="创建服务器说明"
        description="创建新的 Minecraft 服务器。可以使用模板快速创建，或使用传统模式手动编辑 Docker Compose 配置。"
        type="info"
        showIcon
        closable
      />

      <Card>
        <Tabs
          activeKey={creationMode}
          onChange={(key) => setCreationMode(key as CreationMode)}
          items={[
            {
              key: 'template',
              label: (
                <span>
                  <SnippetsOutlined /> 模板模式
                </span>
              ),
              children: (
                <div className="space-y-4">
                  {/* Template Selection */}
                  <Card title="选择模板" size="small">
                    <Select
                      placeholder="选择一个服务器模板"
                      style={{ width: '100%' }}
                      value={selectedTemplateId}
                      onChange={setSelectedTemplateId}
                      loading={templatesLoading}
                      options={templates.map((t) => ({
                        value: t.id,
                        label: `${t.name}${t.description ? ` - ${t.description}` : ''}`,
                      }))}
                      notFoundContent={
                        <Empty
                          description="暂无模板"
                          image={Empty.PRESENTED_IMAGE_SIMPLE}
                        >
                          <Button type="link" onClick={() => navigate('/templates/new')}>
                            创建模板
                          </Button>
                        </Empty>
                      }
                    />
                  </Card>

                  {/* Template Form */}
                  {selectedTemplateId && templateSchema && (
                    <Card
                      title="配置参数"
                      size="small"
                      extra={
                        <Button
                          icon={<EyeOutlined />}
                          onClick={handlePreviewYaml}
                          loading={previewMutation.isPending}
                        >
                          预览 YAML
                        </Button>
                      }
                    >
                      {schemaLoading ? (
                        <div className="text-center py-4">加载中...</div>
                      ) : (
                        <RjsfForm
                          schema={templateSchema.json_schema as RJSFSchema}
                          formData={templateFormData}
                          validator={validator}
                          onChange={handleTemplateFormChange}
                          showErrorList={false}
                          liveValidate
                        >
                          <div /> {/* Hide default submit button */}
                        </RjsfForm>
                      )}
                    </Card>
                  )}

                  {/* Restart Schedule */}
                  <Card title="自动重启计划" size="small">
                    <div className="flex items-center space-x-3">
                      <Switch
                        checked={enableRestartSchedule}
                        onChange={setEnableRestartSchedule}
                        size="default"
                      />
                      <span className={enableRestartSchedule ? 'text-green-600' : 'text-gray-500'}>
                        {enableRestartSchedule ? '已启用' : '已禁用'}
                      </span>
                    </div>
                    {enableRestartSchedule && (
                      <div className="text-sm text-gray-500 mt-2">
                        系统将自动选择与现有备份任务不冲突的时间创建重启计划
                      </div>
                    )}
                  </Card>
                </div>
              ),
            },
            {
              key: 'traditional',
              label: (
                <span>
                  <CodeOutlined /> 传统模式
                </span>
              ),
              children: (
                <Form
                  form={form}
                  layout="vertical"
                  initialValues={{ composeContent: '' }}
                >
                  {/* Server Name */}
                  <Card title="服务器基本信息" size="small" className="mb-4">
                    <Form.Item
                      name="serverName"
                      label="服务器名称"
                      rules={[
                        { required: true, message: '请输入服务器名称' },
                        { pattern: /^[a-zA-Z0-9-_]+$/, message: '服务器名称只能包含字母、数字、连字符和下划线' },
                        { min: 1, max: 50, message: '服务器名称长度应在1-50个字符之间' }
                      ]}
                    >
                      <Input placeholder="例如: vanilla-survival" size="large" />
                    </Form.Item>

                    <Form.Item label="自动重启计划">
                      <div className="flex items-center space-x-3">
                        <Switch
                          checked={enableRestartSchedule}
                          onChange={setEnableRestartSchedule}
                          size="default"
                        />
                        <span className={enableRestartSchedule ? 'text-green-600' : 'text-gray-500'}>
                          {enableRestartSchedule ? '已启用' : '已禁用'}
                        </span>
                      </div>
                    </Form.Item>
                  </Card>

                  {/* Compose Editor */}
                  <Card
                    title="Docker Compose 配置"
                    size="small"
                    extra={
                      <Space>
                        <Button
                          icon={<QuestionCircleOutlined />}
                          onClick={() => setIsHelpModalVisible(true)}
                          type="default"
                        >
                          配置帮助
                        </Button>
                        <Button
                          icon={<CopyOutlined />}
                          onClick={() => setIsTemplateModalVisible(true)}
                          type="dashed"
                        >
                          从现有服务器复制
                        </Button>
                      </Space>
                    }
                  >
                    <Alert
                      message="配置说明"
                      description="注意编辑container_name为mc-{服务器名}; 注意编辑服务器端口，不与现有冲突"
                      type="info"
                      showIcon
                      className="mb-4"
                    />

                    <Form.Item
                      name="composeContent"
                      rules={[{ required: true, message: '请输入 Docker Compose 配置' }]}
                    >
                      <ComposeYamlEditor
                        autoHeight
                        minHeight={300}
                        value={composeContent}
                        onChange={handleComposeContentChange}
                        onMount={(editor: any) => {
                          editorRef.current = editor
                        }}
                        theme="vs-light"
                        path="docker-compose.yml"
                      />
                    </Form.Item>
                  </Card>
                </Form>
              ),
            },
          ]}
        />
      </Card>

      {/* Archive Selection */}
      <Card title="服务器数据 (可选)">
        <div className="space-y-4">
          <Text type="secondary">
            可以选择压缩包文件来填充服务器数据。如果不选择，将创建空的服务器。
          </Text>

          <div className="flex items-center space-x-4">
            <Button
              icon={<FileZipOutlined />}
              onClick={() => setIsArchiveModalVisible(true)}
              size="large"
            >
              选择压缩包文件
            </Button>

            {selectedArchiveFile && (
              <div className="flex items-center space-x-2">
                <Text strong>已选择: {selectedArchiveFile}</Text>
                <Button size="small" type="link" onClick={handleRemoveArchive}>
                  移除
                </Button>
              </div>
            )}
          </div>

          {selectedArchiveFile && (
            <Alert
              message="已选择压缩包文件"
              description={`压缩包 "${selectedArchiveFile}" 将在服务器创建后自动解压到服务器数据目录中。`}
              type="success"
              showIcon
            />
          )}
        </div>
      </Card>

      <Divider />

      {/* Create Button */}
      <Card>
        <div className="flex justify-between items-center">
          <div>
            <Text strong>准备创建服务器</Text>
            <br />
            <Text type="secondary">
              {creationMode === 'template'
                ? selectedTemplateId
                  ? `将使用模板创建服务器`
                  : '请先选择一个模板'
                : composeContent
                  ? '将使用自定义 Docker Compose 配置创建服务器'
                  : '请先输入 Docker Compose 配置'
              }
            </Text>
          </div>
          <Space>
            <Button
              type="primary"
              size="large"
              icon={<PlayCircleOutlined />}
              loading={isLoading}
              onClick={handleCreate}
              disabled={
                creationMode === 'template'
                  ? !selectedTemplateId
                  : !composeContent
              }
            >
              {createServerMutation.isPending
                ? '创建中...'
                : createRestartScheduleMutation.isPending
                  ? '配置重启计划中...'
                  : populateServerMutation.isPending
                    ? '填充数据中...'
                    : '创建服务器'}
            </Button>
          </Space>
        </div>
      </Card>

      {/* Modals */}
      <ArchiveSelectionModal
        open={isArchiveModalVisible}
        onCancel={() => setIsArchiveModalVisible(false)}
        onSelect={handleArchiveSelect}
        title="选择压缩包文件"
        description="选择要用于填充服务器数据的压缩包文件"
      />

      <PopulateProgressModal
        open={isPopulateProgressModalVisible}
        taskId={populateTaskId}
        serverId={createdServerId || ''}
        onClose={handlePopulateClose}
        onComplete={handlePopulateComplete}
      />

      <ServerTemplateModal
        open={isTemplateModalVisible}
        onCancel={() => setIsTemplateModalVisible(false)}
        onSelect={handleTemplateSelect}
        title="选择服务器模板"
        description="选择现有服务器作为模板，使用其 Docker Compose 配置创建新服务器"
        selectButtonText="使用模板"
      />

      <DockerComposeHelpModal
        open={isHelpModalVisible}
        onCancel={() => setIsHelpModalVisible(false)}
      />

      {/* Preview YAML Modal */}
      {previewYaml && (
        <div
          className={`fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 ${isPreviewModalVisible ? '' : 'hidden'}`}
          onClick={() => setIsPreviewModalVisible(false)}
        >
          <div
            className="bg-white rounded-lg p-4 w-3/4 max-h-[80vh] overflow-auto"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex justify-between items-center mb-4">
              <Text strong>预览生成的 YAML</Text>
              <Button onClick={() => setIsPreviewModalVisible(false)}>关闭</Button>
            </div>
            <SimpleEditor
              value={previewYaml}
              language="yaml"
              height="60vh"
              options={{ readOnly: true }}
            />
          </div>
        </div>
      )}
    </div>
  )
}

export default ServerNew
