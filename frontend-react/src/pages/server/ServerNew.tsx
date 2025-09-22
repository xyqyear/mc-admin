import React, { useState, useRef } from 'react'
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
  Divider
} from 'antd'
import {
  FileZipOutlined,
  PlayCircleOutlined,
  PlusOutlined,
  CopyOutlined,
  QuestionCircleOutlined
} from '@ant-design/icons'
import { ComposeYamlEditor } from '@/components/editors'
import PageHeader from '@/components/layout/PageHeader'
import ArchiveSelectionModal from '@/components/modals/ArchiveSelectionModal'
import ServerTemplateModal from '@/components/modals/ServerTemplateModal'
import DockerComposeHelpModal from '@/components/modals/DockerComposeHelpModal'
import { useServerMutations } from '@/hooks/mutations/useServerMutations'
import { useAutoUpdateDNS } from '@/hooks/mutations/useDnsMutations'

const { Text } = Typography


const ServerNew: React.FC = () => {
  const navigate = useNavigate()
  const [form] = Form.useForm()
  const [composeContent, setComposeContent] = useState('')

  // Archive selection state
  const [isArchiveModalVisible, setIsArchiveModalVisible] = useState(false)
  const [selectedArchiveFile, setSelectedArchiveFile] = useState<string | null>(null)

  // Template selection state
  const [isTemplateModalVisible, setIsTemplateModalVisible] = useState(false)

  // Help modal state
  const [isHelpModalVisible, setIsHelpModalVisible] = useState(false)

  // Restart schedule state
  const [enableRestartSchedule, setEnableRestartSchedule] = useState(true)

  // Use mutations
  const { useCreateServer, usePopulateServer, useCreateOrUpdateRestartSchedule } = useServerMutations()
  const createServerMutation = useCreateServer()
  const populateServerMutation = usePopulateServer()
  const createRestartScheduleMutation = useCreateOrUpdateRestartSchedule()
  const autoUpdateDNS = useAutoUpdateDNS()

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

  const handleCreate = async () => {
    try {
      const values = await form.validateFields()

      // 创建服务器
      await createServerMutation.mutateAsync({
        serverId: values.serverName,
        yamlContent: composeContent,
      })

      // 如果启用了重启计划，创建重启计划
      if (enableRestartSchedule) {
        try {
          await createRestartScheduleMutation.mutateAsync({
            serverId: values.serverName,
          })
        } catch {
          // 重启计划创建失败，但不阻止整个流程
        }
      }

      if (selectedArchiveFile) {
        // 如果选择了压缩包，填充服务器数据
        try {
          await populateServerMutation.mutateAsync({
            serverId: values.serverName,
            archiveFilename: selectedArchiveFile,
          })
          message.success(`服务器 "${values.serverName}" 创建并填充完成!`)
        } catch (populateError: any) {
          // 创建成功但填充失败，提示用户
          message.warning(`服务器 "${values.serverName}" 创建成功，但数据填充失败: ${populateError.message || '未知错误'}`)
        }
      }

      // 服务器创建完成后，自动触发DNS更新
      try {
        await autoUpdateDNS.mutateAsync()
      } catch (dnsError: any) {
        // DNS更新失败不阻止页面跳转，错误已在mutation中处理
        console.warn('DNS自动更新失败:', dnsError)
      }

      navigate('/overview')
    } catch (error: any) {
      // Errors are already handled by mutations
      console.error('创建服务器过程中出错:', error)
    }
  }

  const handleComposeContentChange = (value: string | undefined) => {
    if (value !== undefined) {
      setComposeContent(value)
      form.setFieldsValue({ composeContent: value })
    }
  }

  // 同步默认compose内容到表单
  React.useEffect(() => {
    form.setFieldsValue({ composeContent: composeContent })
  }, [form, composeContent])

  const editorRef = useRef<any>(null)


  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <PageHeader
        title="新建服务器"
        icon={<PlusOutlined />}
      />

      <Alert
        message="创建服务器说明"
        description="创建新的 Minecraft 服务器。可以选择压缩包文件来填充服务器数据，或只使用 Docker Compose 配置创建空服务器。"
        type="info"
        showIcon
        closable
      />

      <Form
        form={form}
        layout="vertical"
        onFinish={handleCreate}
        initialValues={{
          composeContent: ''
        }}
      >


        {/* 第一部分：服务器名字 */}
        <Card title="服务器基本信息" className="mb-6">
          <Form.Item
            name="serverName"
            label="服务器名称"
            rules={[
              { required: true, message: '请输入服务器名称' },
              { pattern: /^[a-zA-Z0-9-_]+$/, message: '服务器名称只能包含字母、数字、连字符和下划线' },
              { min: 1, max: 50, message: '服务器名称长度应在1-50个字符之间' }
            ]}
          >
            <Input
              placeholder="例如: vanilla-survival"
              size="large"
            />
          </Form.Item>

          <Form.Item
            label="自动重启计划"
            tooltip="启用后将自动为服务器创建重启计划，避免与现有备份任务的时间冲突"
          >
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
          </Form.Item>
        </Card>

        {/* 第三部分：Compose文件编辑 */}
        <Card
          title="Docker Compose 配置"
          className="mb-6"
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
                选择模板
              </Button>
            </Space>
          }
        >
          <div className="space-y-4">
            <Alert
              message="配置说明"
              description="注意编辑container_name为mc-{服务器名}; 注意编辑服务器端口，不与现有冲突"
              type="info"
              showIcon
            />

            <Form.Item
              name="composeContent"
              rules={[{ required: true, message: '请输入 Docker Compose 配置' }]}
            >
              <ComposeYamlEditor
                height="500px"
                value={composeContent}
                onChange={handleComposeContentChange}
                onMount={(editor: any) => {
                  editorRef.current = editor
                }}
                theme="vs-light"
                path="docker-compose.yml"
              />
            </Form.Item>
          </div>
        </Card>

        {/* 第二部分：可选的压缩包选择 */}
        <Card title="服务器数据 (可选)" className="mb-6">
          <div className="space-y-4">
            <Text type="secondary">
              可以选择压缩包文件来填充服务器数据。如果不选择，将创建空的服务器。压缩包中需要包含server.properties文件
              <br />
              server.properties将会被上方的 Docker Compose 配置中的配置项覆盖
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
                  <Button
                    size="small"
                    type="link"
                    onClick={handleRemoveArchive}
                  >
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

        {/* 创建按钮区域 */}
        <Card>
          <div className="flex justify-between items-center">
            <div>
              <Text strong>准备创建服务器</Text>
              <br />
              <Text type="secondary">
                {selectedArchiveFile
                  ? `将使用压缩包 "${selectedArchiveFile}" 填充服务器数据`
                  : composeContent
                    ? '将使用自定义 Docker Compose 配置创建服务器'
                    : '请先选择模板或输入 Docker Compose 配置'
                }
              </Text>
            </div>
            <Space>
              <Button
                type="primary"
                size="large"
                icon={<PlayCircleOutlined />}
                loading={createServerMutation.isPending || populateServerMutation.isPending || createRestartScheduleMutation.isPending}
                onClick={handleCreate}
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
      </Form>

      {/* 压缩包选择弹窗 */}
      <ArchiveSelectionModal
        open={isArchiveModalVisible}
        onCancel={() => setIsArchiveModalVisible(false)}
        onSelect={handleArchiveSelect}
        title="选择压缩包文件"
        description="选择要用于填充服务器数据的压缩包文件"
      />

      {/* 服务器模板选择弹窗 */}
      <ServerTemplateModal
        open={isTemplateModalVisible}
        onCancel={() => setIsTemplateModalVisible(false)}
        onSelect={handleTemplateSelect}
        title="选择服务器模板"
        description="选择现有服务器作为模板，使用其 Docker Compose 配置创建新服务器"
        selectButtonText="使用模板"
      />

      {/* Docker Compose 配置帮助弹窗 */}
      <DockerComposeHelpModal
        open={isHelpModalVisible}
        onCancel={() => setIsHelpModalVisible(false)}
      />
    </div>
  )
}

export default ServerNew
