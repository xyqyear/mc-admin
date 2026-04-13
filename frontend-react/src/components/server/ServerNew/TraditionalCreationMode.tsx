import React, { useState, useRef } from 'react'
import { toast } from 'sonner'
import { Copy, HelpCircle } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Field, FieldError, FieldLabel } from '@/components/ui/field'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Alert, AlertTitle, AlertDescription } from '@/components/ui/alert'

import { ComposeYamlEditor } from '@/components/editors'
import ServerTemplateDialog from '@/components/dialogs/ServerTemplateDialog'
import DockerComposeHelpDialog from '@/components/dialogs/DockerComposeHelpDialog'

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
  const [isTemplateDialogOpen, setIsTemplateDialogOpen] = useState(false)
  const [isHelpDialogOpen, setIsHelpDialogOpen] = useState(false)
  const editorRef = useRef<any>(null)

  const handleTemplateSelect = (templateContent: string) => {
    setComposeContent(templateContent)
    setIsTemplateDialogOpen(false)
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
        <CardContent>
          <Field data-invalid={!!serverNameError || undefined}>
            <FieldLabel htmlFor="server-name">服务器名称</FieldLabel>
            <Input
              id="server-name"
              placeholder="例如: vanilla-survival"
              value={serverName}
              onChange={(e) => {
                setServerName(e.target.value)
                if (serverNameError) setServerNameError('')
              }}
              aria-invalid={!!serverNameError || undefined}
              className="max-w-md"
            />
            {serverNameError && <FieldError>{serverNameError}</FieldError>}
          </Field>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-2 flex-row items-center justify-between space-y-0">
          <CardTitle className="text-sm">Docker Compose 配置</CardTitle>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setIsHelpDialogOpen(true)}
            >
              <HelpCircle className="mr-1 h-4 w-4" />
              配置帮助
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setIsTemplateDialogOpen(true)}
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
            path="docker-compose.yml"
          />
        </CardContent>
      </Card>

      <ServerTemplateDialog
        open={isTemplateDialogOpen}
        onCancel={() => setIsTemplateDialogOpen(false)}
        onSelect={handleTemplateSelect}
        title="选择服务器模板"
        description="选择现有服务器作为模板，使用其 Docker Compose 配置创建新服务器"
        selectButtonText="使用模板"
      />

      <DockerComposeHelpDialog
        open={isHelpDialogOpen}
        onCancel={() => setIsHelpDialogOpen(false)}
      />
    </div>
  )
}

export default TraditionalCreationMode
