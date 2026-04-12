import React, { useState, useRef } from 'react'
import { toast } from 'sonner'
import { Copy, HelpCircle } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Alert, AlertTitle, AlertDescription } from '@/components/ui/alert'

import { ComposeYamlEditor } from '@/components/editors'
import ServerTemplateModal from '@/components/modals/ServerTemplateModal'
import DockerComposeHelpModal from '@/components/modals/DockerComposeHelpModal'

interface TraditionalCreationModeProps {
  serverName: string
  setServerName: (name: string) => void
  serverNameError: string
  setServerNameError: (error: string) => void
  composeContent: string
  setComposeContent: (content: string) => void
}

const TraditionalCreationMode: React.FC<TraditionalCreationModeProps> = ({
  serverName,
  setServerName,
  serverNameError,
  setServerNameError,
  composeContent,
  setComposeContent,
}) => {
  const [isTemplateModalVisible, setIsTemplateModalVisible] = useState(false)
  const [isHelpModalVisible, setIsHelpModalVisible] = useState(false)
  const editorRef = useRef<any>(null)

  const handleTemplateSelect = (templateContent: string) => {
    setComposeContent(templateContent)
    setIsTemplateModalVisible(false)
    toast.success('已应用服务器模板配置')
  }

  const handleComposeContentChange = (value: string | undefined) => {
    if (value !== undefined) {
      setComposeContent(value)
    }
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm">服务器基本信息</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          <Label>服务器名称</Label>
          <Input
            placeholder="例如: vanilla-survival"
            value={serverName}
            onChange={(e) => {
              setServerName(e.target.value)
              if (serverNameError) setServerNameError('')
            }}
            className="max-w-md"
          />
          {serverNameError && <p className="text-sm text-destructive">{serverNameError}</p>}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-2 flex-row items-center justify-between space-y-0">
          <CardTitle className="text-sm">Docker Compose 配置</CardTitle>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setIsHelpModalVisible(true)}
            >
              <HelpCircle className="mr-1 h-4 w-4" />
              配置帮助
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setIsTemplateModalVisible(true)}
            >
              <Copy className="mr-1 h-4 w-4" />
              从现有服务器复制
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <Alert>
            <AlertTitle>配置说明</AlertTitle>
            <AlertDescription>注意编辑container_name为mc-{'{服务器名}'}; 注意编辑服务器端口，不与现有冲突</AlertDescription>
          </Alert>

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
        </CardContent>
      </Card>

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
    </div>
  )
}

export default TraditionalCreationMode
