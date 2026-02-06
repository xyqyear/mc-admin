import React, { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Card,
  Form,
  Button,
  Typography,
  Alert,
  Space,
  Switch,
  message,
  Divider,
  Tabs,
} from 'antd'
import {
  FileZipOutlined,
  PlayCircleOutlined,
  PlusOutlined,
  SnippetsOutlined,
  CodeOutlined,
} from '@ant-design/icons'
import PageHeader from '@/components/layout/PageHeader'
import ArchiveSelectionModal from '@/components/modals/ArchiveSelectionModal'
import PopulateProgressModal from '@/components/modals/PopulateProgressModal'
import { TemplateCreationMode, TraditionalCreationMode } from '@/components/server/ServerNew'
import { useServerMutations } from '@/hooks/mutations/useServerMutations'
import { useAutoUpdateDNS } from '@/hooks/mutations/useDnsMutations'
import { useTemplateSchema, useAvailablePorts } from '@/hooks/queries/base/useTemplateQueries'
import validator from '@rjsf/validator-ajv8'
import type { RJSFSchema } from '@rjsf/utils'

const { Text } = Typography

type CreationMode = 'traditional' | 'template'

const ServerNew: React.FC = () => {
  const navigate = useNavigate()
  const [form] = Form.useForm()

  // Creation mode state
  const [creationMode, setCreationMode] = useState<CreationMode>('template')

  // Template mode state (managed by parent for validation and creation)
  const [selectedTemplateId, setSelectedTemplateId] = useState<number | null>(null)
  const [templateFormData, setTemplateFormData] = useState<Record<string, unknown>>({})

  // Traditional mode state
  const [composeContent, setComposeContent] = useState('')

  // Archive selection state
  const [isArchiveModalVisible, setIsArchiveModalVisible] = useState(false)
  const [selectedArchiveFile, setSelectedArchiveFile] = useState<string | null>(null)

  // Populate progress state
  const [populateTaskId, setPopulateTaskId] = useState<string | null>(null)
  const [isPopulateProgressModalVisible, setIsPopulateProgressModalVisible] = useState(false)
  const [createdServerId, setCreatedServerId] = useState<string | null>(null)

  // Restart schedule state
  const [enableRestartSchedule, setEnableRestartSchedule] = useState(true)

  // Queries for template validation
  const { data: templateSchema } = useTemplateSchema(selectedTemplateId)
  const { data: availablePorts } = useAvailablePorts(creationMode === 'template')

  // Mutations
  const { useCreateServer, usePopulateServer, useCreateOrUpdateRestartSchedule } = useServerMutations()
  const createServerMutation = useCreateServer()
  const populateServerMutation = usePopulateServer()
  const createRestartScheduleMutation = useCreateOrUpdateRestartSchedule()
  const autoUpdateDNS = useAutoUpdateDNS()

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

  // Sync compose content with form
  useEffect(() => {
    form.setFieldsValue({ composeContent: composeContent })
  }, [form, composeContent])

  const handleArchiveSelect = (filename: string) => {
    setSelectedArchiveFile(filename)
    setIsArchiveModalVisible(false)
    message.success(`已选择压缩包: ${filename}`)
  }

  const handleRemoveArchive = () => {
    setSelectedArchiveFile(null)
    message.info('已移除压缩包选择')
  }

  const triggerDNSUpdateAndNavigate = async () => {
    try {
      await autoUpdateDNS.mutateAsync()
    } catch (dnsError: any) {
      console.warn('DNS自动更新失败:', dnsError)
    }
    navigate('/overview')
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

  const isLoading = createServerMutation.isPending || populateServerMutation.isPending || createRestartScheduleMutation.isPending

  // Validate template form data against schema
  const isTemplateFormValid = !!selectedTemplateId && !!templateSchema?.json_schema &&
    validator.isValid(templateSchema.json_schema as RJSFSchema, templateFormData, templateSchema.json_schema as RJSFSchema)

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
                <TemplateCreationMode
                  selectedTemplateId={selectedTemplateId}
                  setSelectedTemplateId={setSelectedTemplateId}
                  templateFormData={templateFormData}
                  setTemplateFormData={setTemplateFormData}
                />
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
                <TraditionalCreationMode
                  form={form}
                  composeContent={composeContent}
                  setComposeContent={setComposeContent}
                />
              ),
            },
          ]}
        />
      </Card>

      {/* Restart Schedule */}
      <Card title="自动重启计划">
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
                ? isTemplateFormValid
                  ? '将使用模板创建服务器'
                  : selectedTemplateId
                    ? '请填写所有必填参数'
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
                  ? !isTemplateFormValid
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

      {/* Shared Modals */}
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
    </div>
  )
}

export default ServerNew
