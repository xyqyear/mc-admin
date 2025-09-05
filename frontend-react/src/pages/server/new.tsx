import React, { useState, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Card,
  Form,
  Input,
  Button,
  Upload,
  Typography,
  Alert,
  Space,
  message
} from 'antd'
import {
  UploadOutlined,
  PlayCircleOutlined
} from '@ant-design/icons'
import { ComposeYamlEditor } from '@/components/editors'
import type { UploadFile } from 'antd/es/upload/interface'

const { Title, Text } = Typography

const defaultComposeContent = `version: '3.8'

services:
  minecraft:
    image: itzg/minecraft-server:latest
    container_name: mc-\${SERVER_NAME}
    ports:
      - "\${SERVER_PORT}:25565"
    environment:
      EULA: "TRUE"
      TYPE: "VANILLA"
      VERSION: "LATEST"
      MEMORY: "2G"
      DIFFICULTY: "normal"
      OPS_FILE: "/ops.json"
      MOTD: "Welcome to \${SERVER_NAME}!"
      ENABLE_RCON: "true"
      RCON_PASSWORD: "minecraft"
      RCON_PORT: 25575
    volumes:
      - ./data:/data
      - ./ops.json:/ops.json:ro
    restart: unless-stopped
    stdin_open: true
    tty: true

volumes:
  data:`

const ServerNew: React.FC = () => {
  const navigate = useNavigate()
  const [form] = Form.useForm()
  const [fileList, setFileList] = useState<UploadFile[]>([])
  const [composeContent, setComposeContent] = useState(defaultComposeContent)
  const [isCreating, setIsCreating] = useState(false)

  const handleUploadChange = (info: any) => {
    setFileList(info.fileList.slice(-1)) // Only keep the latest file
  }

  const beforeUpload = (file: File) => {
    const isZip = file.type === 'application/zip' || file.name.endsWith('.zip')
    if (!isZip) {
      message.error('只能上传 ZIP 文件!')
      return false
    }
    const isLt100M = file.size / 1024 / 1024 < 100
    if (!isLt100M) {
      message.error('文件大小不能超过 100MB!')
      return false
    }
    return false // Prevent automatic upload, we'll handle it manually
  }

  const handleCreate = async () => {
    try {
      const values = await form.validateFields()
      setIsCreating(true)

      // Simulate server creation
      setTimeout(() => {
        setIsCreating(false)
        message.success(`服务器 "${values.serverName}" 创建成功!`)
        navigate('/overview')
      }, 2000)
    } catch (error) {
      console.error('Validation failed:', error)
    }
  }

  const handleComposeContentChange = (value: string | undefined) => {
    if (value !== undefined) {
      setComposeContent(value)
    }
  }

  const editorRef = useRef<any>(null)

  const insertVariable = (variable: string) => {
    const editor = editorRef.current
    if (editor) {
      const model = editor.getModel()
      const selection = editor.getSelection()

      if (model && selection) {
        const range = {
          startLineNumber: selection.startLineNumber,
          startColumn: selection.startColumn,
          endLineNumber: selection.endLineNumber,
          endColumn: selection.endColumn
        }

        editor.executeEdits('insert-variable', [
          {
            range: range,
            text: variable
          }
        ])

        // Set cursor position after the inserted text
        const newPosition = {
          lineNumber: selection.startLineNumber,
          column: selection.startColumn + variable.length
        }
        editor.setPosition(newPosition)
        editor.focus()
      }
    }
  }

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div>
        <Title level={2}>创建新服务器</Title>
        <Text type="secondary">
          上传服务器文件包或使用默认配置创建新的 Minecraft 服务器
        </Text>
      </div>

      <Alert
        message="创建服务器提示"
        description="您可以上传包含服务器文件的 ZIP 包，或者使用默认的 Docker Compose 配置创建新服务器。ZIP 包会被解压到服务器目录中。"
        type="info"
        showIcon
        closable
      />

      <Form
        form={form}
        layout="vertical"
        onFinish={handleCreate}
      >
        <Card title="基本信息" className="mb-6">
          <Form.Item
            name="serverName"
            label="服务器名称"
            rules={[
              { required: true, message: '请输入服务器名称' },
              { pattern: /^[a-zA-Z0-9-_]+$/, message: '服务器名称只能包含字母、数字、连字符和下划线' }
            ]}
          >
            <Input
              placeholder="例如: vanilla-survival"
              onChange={(e) => {
                const newContent = composeContent.replace(/\${SERVER_NAME}/g, e.target.value || '${SERVER_NAME}')
                setComposeContent(newContent)
              }}
            />
          </Form.Item>

          <Form.Item
            name="serverPort"
            label="服务器端口"
            rules={[
              { required: true, message: '请输入服务器端口' },
              { pattern: /^\d+$/, message: '端口必须是数字' }
            ]}
            initialValue="25565"
          >
            <Input
              placeholder="25565"
              onChange={(e) => {
                const newContent = composeContent.replace(/\${SERVER_PORT}/g, e.target.value || '${SERVER_PORT}')
                setComposeContent(newContent)
              }}
            />
          </Form.Item>

          <Form.Item
            name="description"
            label="服务器描述"
          >
            <Input.TextArea
              rows={3}
              placeholder="输入服务器描述 (可选)"
              maxLength={200}
              showCount
            />
          </Form.Item>
        </Card>

        <Card title="服务器文件" className="mb-6">
          <Form.Item
            name="serverFiles"
            label="服务器文件包 (可选)"
            extra="上传包含服务器配置、世界文件、插件等的 ZIP 包。如果不上传，将使用默认配置创建新服务器。"
          >
            <Upload
              accept=".zip"
              beforeUpload={beforeUpload}
              onChange={handleUploadChange}
              fileList={fileList}
              maxCount={1}
            >
              <Button icon={<UploadOutlined />}>
                选择 ZIP 文件 (最大 100MB)
              </Button>
            </Upload>
          </Form.Item>
        </Card>

        <Card title="Docker Compose 配置" className="mb-6">
          <div className="mb-4">
            <Text strong>快速插入变量：</Text>
            <Space className="ml-2">
              <Button
                size="small"
                type="link"
                onClick={() => insertVariable('${SERVER_NAME}')}
              >
                ${'{'}SERVER_NAME{'}'}
              </Button>
              <Button
                size="small"
                type="link"
                onClick={() => insertVariable('${SERVER_PORT}')}
              >
                ${'{'}SERVER_PORT{'}'}
              </Button>
            </Space>
          </div>

          <Form.Item
            name="composeContent"
            label="docker-compose.yml 内容"
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

          <Alert
            message="配置说明"
            description="这是服务器的 Docker Compose 配置文件。您可以修改环境变量、端口映射、卷挂载等设置。${SERVER_NAME} 和 ${SERVER_PORT} 变量会自动替换为上面输入的值。"
            type="info"
            showIcon
            className="mt-4"
          />
        </Card>

        <Card>
          <div className="flex justify-between items-center">
            <div>
              <Text strong>准备创建服务器</Text>
              <br />
              <Text type="secondary">
                请确认上述配置信息，点击创建按钮开始部署服务器
              </Text>
            </div>
            <Space>
              <Button
                onClick={() => navigate('/overview')}
              >
                取消
              </Button>
              <Button
                type="primary"
                icon={<PlayCircleOutlined />}
                loading={isCreating}
                onClick={handleCreate}
              >
                {isCreating ? '创建中...' : '创建服务器'}
              </Button>
            </Space>
          </div>
        </Card>
      </Form>
    </div>
  )
}

export default ServerNew
