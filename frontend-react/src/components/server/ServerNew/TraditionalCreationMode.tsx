import React, { useState, useRef } from 'react'
import { Card, Form, Input, Button, Alert, Space } from 'antd'
import { CopyOutlined, QuestionCircleOutlined } from '@ant-design/icons'
import type { FormInstance } from 'antd'
import { ComposeYamlEditor } from '@/components/editors'
import ServerTemplateModal from '@/components/modals/ServerTemplateModal'
import DockerComposeHelpModal from '@/components/modals/DockerComposeHelpModal'
import { message } from 'antd'

interface TraditionalCreationModeProps {
  form: FormInstance
  composeContent: string
  setComposeContent: (content: string) => void
}

const TraditionalCreationMode: React.FC<TraditionalCreationModeProps> = ({
  form,
  composeContent,
  setComposeContent,
}) => {
  // Internal state
  const [isTemplateModalVisible, setIsTemplateModalVisible] = useState(false)
  const [isHelpModalVisible, setIsHelpModalVisible] = useState(false)
  const editorRef = useRef<any>(null)

  const handleTemplateSelect = (templateContent: string) => {
    setComposeContent(templateContent)
    setIsTemplateModalVisible(false)
    form.setFieldsValue({ composeContent: templateContent })
    message.success('已应用服务器模板配置')
  }

  const handleComposeContentChange = (value: string | undefined) => {
    if (value !== undefined) {
      setComposeContent(value)
      form.setFieldsValue({ composeContent: value })
    }
  }

  return (
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

      {/* Modals */}
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
    </Form>
  )
}

export default TraditionalCreationMode
