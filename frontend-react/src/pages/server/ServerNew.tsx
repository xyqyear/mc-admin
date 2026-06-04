import React, { useState, useEffect } from 'react'
import { useNavigate } from 'react-router'
import { toast } from 'sonner'
import {
  FileArchive,
  Play,
  Plus,
  FileText,
  Code,
} from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Alert, AlertTitle, AlertDescription } from '@/components/ui/alert'
import { Separator } from '@/components/ui/separator'
import { Switch } from '@/components/ui/switch'
import { Spinner } from '@/components/ui/spinner'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'

import PageHeader from '@/components/layout/PageHeader'
import ArchiveSelectionDialog from '@/components/dialogs/ArchiveSelectionDialog'
import PopulateProgressDialog from '@/components/dialogs/PopulateProgressDialog'
import { TemplateCreationMode, TraditionalCreationMode } from '@/components/server/ServerNew'
import { useServerMutations } from '@/hooks/mutations/useServerMutations'
import { useTemplateSchema, useAvailablePorts } from '@/hooks/queries/base/useTemplateQueries'
import validator from '@rjsf/validator-ajv8'
import type { RJSFSchema } from '@rjsf/utils'

type CreationMode = 'traditional' | 'template'

const ServerNew: React.FC = () => {
  const navigate = useNavigate()

  const [creationMode, setCreationMode] = useState<CreationMode>('template')

  const [selectedTemplateId, setSelectedTemplateId] = useState<number | null>(null)
  const [templateFormData, setTemplateFormData] = useState<Record<string, unknown>>({})

  const [serverName, setServerName] = useState('')
  const [serverNameError, setServerNameError] = useState('')
  const [composeContent, setComposeContent] = useState('')

  const [isArchiveDialogOpen, setIsArchiveDialogOpen] = useState(false)
  const [selectedArchiveFile, setSelectedArchiveFile] = useState<string | null>(null)

  const [populateTaskId, setPopulateTaskId] = useState<string | null>(null)
  const [isPopulateProgressDialogOpen, setIsPopulateProgressDialogOpen] = useState(false)
  const [createdServerId, setCreatedServerId] = useState<string | null>(null)

  const [enableRestartSchedule, setEnableRestartSchedule] = useState(true)

  const { data: templateSchema } = useTemplateSchema(selectedTemplateId)
  const { data: availablePorts } = useAvailablePorts(creationMode === 'template')

  const { useCreateServer, usePopulateServer } = useServerMutations()
  const createServerMutation = useCreateServer()
  const populateServerMutation = usePopulateServer()

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

      if (availablePorts) {
        defaults.game_port = availablePorts.suggested_game_port
        defaults.rcon_port = availablePorts.suggested_rcon_port
      }

      setTemplateFormData(defaults)
    }
  }, [templateSchema, availablePorts])

  const handleArchiveSelect = (filename: string) => {
    setSelectedArchiveFile(filename)
    setIsArchiveDialogOpen(false)
    toast.success(`已选择压缩包: ${filename}`)
  }

  const handleRemoveArchive = () => {
    setSelectedArchiveFile(null)
    toast.info('已移除压缩包选择')
  }

  const validateServerName = (): boolean => {
    if (!serverName.trim()) {
      setServerNameError('请输入服务器名称')
      return false
    }
    if (!/^[a-zA-Z0-9-_]+$/.test(serverName)) {
      setServerNameError('服务器名称只能包含字母、数字、连字符和下划线')
      return false
    }
    if (serverName.length > 50) {
      setServerNameError('服务器名称长度应在1-50个字符之间')
      return false
    }
    setServerNameError('')
    return true
  }

  const handleCreate = async () => {
    try {
      let createdName: string

      if (creationMode === 'template') {
        if (!selectedTemplateId) {
          toast.error('请选择一个模板')
          return
        }

        const templateServerName = templateFormData.name as string
        if (!templateServerName) {
          toast.error('请填写服务器名称')
          return
        }

        await createServerMutation.mutateAsync({
          serverId: templateServerName,
          templateId: selectedTemplateId,
          variableValues: templateFormData,
          restartSchedule: enableRestartSchedule ? {} : null,
        })
        createdName = templateServerName
      } else {
        if (!validateServerName()) return
        if (!composeContent.trim()) {
          toast.error('请输入 Docker Compose 配置')
          return
        }

        await createServerMutation.mutateAsync({
          serverId: serverName,
          yamlContent: composeContent,
          restartSchedule: enableRestartSchedule ? {} : null,
        })
        createdName = serverName
      }

      if (selectedArchiveFile) {
        try {
          const result = await populateServerMutation.mutateAsync({
            serverId: createdName,
            archiveFilename: selectedArchiveFile,
          })
          setCreatedServerId(createdName)
          setPopulateTaskId(result.task_id)
          setIsPopulateProgressDialogOpen(true)
        } catch (populateError: any) {
          toast.warning(`服务器 "${createdName}" 创建成功，但数据填充失败: ${populateError.message || '未知错误'}`)
          navigate('/overview')
        }
      } else {
        navigate('/overview')
      }
    } catch (error: any) {
      console.error('创建服务器过程中出错:', error)
    }
  }

  const handlePopulateComplete = async () => {
    setIsPopulateProgressDialogOpen(false)
    setPopulateTaskId(null)
    toast.success(`服务器 "${createdServerId}" 创建并填充完成!`)
    navigate('/overview')
  }

  const handlePopulateClose = () => {
    setIsPopulateProgressDialogOpen(false)
    setPopulateTaskId(null)
    navigate('/overview')
  }

  const isLoading = createServerMutation.isPending || populateServerMutation.isPending

  const isTemplateFormValid = !!selectedTemplateId && !!templateSchema?.json_schema &&
    validator.isValid(templateSchema.json_schema as RJSFSchema, templateFormData, templateSchema.json_schema as RJSFSchema)

  return (
    <div className="space-y-4">
      <PageHeader
        title="新建服务器"
        icon={<Plus className="h-5 w-5" />}
      />

      <Alert>
        <AlertTitle>创建服务器说明</AlertTitle>
        <AlertDescription>
          创建新的 Minecraft 服务器。可以使用模板快速创建，或使用传统模式手动编辑 Docker Compose 配置。
        </AlertDescription>
      </Alert>

      <Card>
        <CardContent className="pt-6">
          <Tabs value={creationMode} onValueChange={(key) => setCreationMode(key as CreationMode)}>
            <TabsList>
              <TabsTrigger value="template">
                <FileText className="mr-1 h-4 w-4" />
                模板模式
              </TabsTrigger>
              <TabsTrigger value="traditional">
                <Code className="mr-1 h-4 w-4" />
                传统模式
              </TabsTrigger>
            </TabsList>
            <TabsContent value="template">
              <TemplateCreationMode
                selectedTemplateId={selectedTemplateId}
                setSelectedTemplateId={setSelectedTemplateId}
                templateFormData={templateFormData}
                setTemplateFormData={setTemplateFormData}
              />
            </TabsContent>
            <TabsContent value="traditional">
              <TraditionalCreationMode
                serverName={serverName}
                setServerName={setServerName}
                serverNameError={serverNameError}
                setServerNameError={setServerNameError}
                composeContent={composeContent}
                setComposeContent={setComposeContent}
              />
            </TabsContent>
          </Tabs>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>自动重启计划</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center gap-3">
            <Switch
              checked={enableRestartSchedule}
              onCheckedChange={setEnableRestartSchedule}
            />
            <span className={enableRestartSchedule ? 'text-green-600' : 'text-muted-foreground'}>
              {enableRestartSchedule ? '已启用' : '已禁用'}
            </span>
          </div>
          {enableRestartSchedule && (
            <p className="text-sm text-muted-foreground mt-2">
              系统将自动选择与现有备份任务不冲突的时间创建重启计划
            </p>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>服务器数据 (可选)</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm text-muted-foreground">
            可以选择压缩包文件来填充服务器数据。如果不选择，将创建空的服务器。
          </p>

          <div className="flex items-center gap-4">
            <Button
              variant="outline"
              onClick={() => setIsArchiveDialogOpen(true)}
            >
              <FileArchive className="mr-1 h-4 w-4" />
              选择压缩包文件
            </Button>

            {selectedArchiveFile && (
              <div className="flex items-center gap-2">
                <span className="font-semibold">已选择: {selectedArchiveFile}</span>
                <Button variant="link" size="sm" onClick={handleRemoveArchive}>
                  移除
                </Button>
              </div>
            )}
          </div>

          {selectedArchiveFile && (
            <Alert>
              <AlertTitle className="text-green-600">已选择压缩包文件</AlertTitle>
              <AlertDescription>压缩包 &quot;{selectedArchiveFile}&quot; 将在服务器创建后自动解压到服务器数据目录中。</AlertDescription>
            </Alert>
          )}
        </CardContent>
      </Card>

      <Separator />

      <Card>
        <CardContent className="pt-6">
          <div className="flex justify-between items-center">
            <div>
              <p className="font-semibold">准备创建服务器</p>
              <p className="text-sm text-muted-foreground">
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
              </p>
            </div>
            <Button
              onClick={handleCreate}
              disabled={
                isLoading || (
                  creationMode === 'template'
                    ? !isTemplateFormValid
                    : !composeContent
                )
              }
            >
              {isLoading ? (
                <Spinner className="mr-2 size-4" />
              ) : (
                <Play className="mr-1 h-4 w-4" />
              )}
              {createServerMutation.isPending
                ? '创建中...'
                : populateServerMutation.isPending
                  ? '填充数据中...'
                  : '创建服务器'}
            </Button>
          </div>
        </CardContent>
      </Card>

      <ArchiveSelectionDialog
        open={isArchiveDialogOpen}
        onCancel={() => setIsArchiveDialogOpen(false)}
        onSelect={handleArchiveSelect}
        title="选择压缩包文件"
        description="选择要用于填充服务器数据的压缩包文件"
      />

      <PopulateProgressDialog
        open={isPopulateProgressDialogOpen}
        taskId={populateTaskId}
        serverId={createdServerId || ''}
        onClose={handlePopulateClose}
        onComplete={handlePopulateComplete}
      />
    </div>
  )
}

export default ServerNew
