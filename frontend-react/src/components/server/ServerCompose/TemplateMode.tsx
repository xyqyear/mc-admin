import React, { useState, useEffect } from 'react'
import { toast } from 'sonner'
import {
  RefreshCw,
  Server,
  GitCompare,
  ArrowLeftRight,
  RefreshCcw,
  Settings,
} from 'lucide-react'
import { Link } from 'react-router'
import type { UseQueryResult } from '@tanstack/react-query'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Alert, AlertTitle, AlertDescription } from '@/components/ui/alert'
import { Spinner } from '@/components/ui/spinner'

import RjsfForm from '@/components/forms/rjsfTheme'
import validator from '@rjsf/validator-ajv8'
import type { RJSFSchema, UiSchema } from '@rjsf/utils'
import { ComposeDiffDialog } from '@/components/dialogs/ServerCompose'
import RebuildProgressDialog from '@/components/dialogs/RebuildProgressDialog'
import ConvertModeDialog from '@/components/dialogs/ConvertModeDialog'
import PageHeader from '@/components/layout/PageHeader'
import { useConfirm } from '@/hooks/useConfirm'
import { useTemplateMutations } from '@/hooks/mutations/useTemplateMutations'

interface TemplateConfig {
  template_id: number
  template_name: string
  variable_values: Record<string, unknown>
  json_schema: object
  snapshot_time: string
  has_template_update: boolean
  template_deleted: boolean
}

interface ServerInfo {
  name: string
}

interface TemplateModeProps {
  serverId: string
  serverInfo: ServerInfo
  templateConfig: TemplateConfig
  composeContent: string
  composeQuery: UseQueryResult<string, Error>
  refetchTemplateConfig: () => void
  rebuildTaskId: string | null
  setRebuildTaskId: (id: string | null) => void
  isRebuildDialogOpen: boolean
  setIsRebuildDialogOpen: (visible: boolean) => void
  isConvertDialogOpen: boolean
  setIsConvertDialogOpen: (visible: boolean) => void
  onConvertModeSuccess: () => void
}

const TemplateMode: React.FC<TemplateModeProps> = ({
  serverId,
  serverInfo,
  templateConfig,
  composeContent,
  composeQuery,
  refetchTemplateConfig,
  rebuildTaskId,
  setRebuildTaskId,
  isRebuildDialogOpen,
  setIsRebuildDialogOpen,
  isConvertDialogOpen,
  setIsConvertDialogOpen,
  onConvertModeSuccess,
}) => {
  const { confirm, confirmDialog } = useConfirm()

  const { useUpdateServerTemplateConfig, usePreviewRenderedYaml } = useTemplateMutations()
  const updateTemplateConfigMutation = useUpdateServerTemplateConfig()
  const previewMutation = usePreviewRenderedYaml()

  const [templateFormData, setTemplateFormData] = useState<Record<string, unknown>>({})
  const [previewYaml, setPreviewYaml] = useState<string | null>(null)
  const [isTemplateDiffVisible, setIsTemplateDiffVisible] = useState(false)
  const [templateDiffLoading, setTemplateDiffLoading] = useState(false)
  const [isUpdateDialogOpen, setIsUpdateDialogOpen] = useState(false)

  const templateUiSchema: UiSchema = {
    name: {
      "ui:disabled": true,
      "ui:help": "服务器名称不可修改",
    },
  }

  useEffect(() => {
    if (templateConfig?.variable_values) {
      setTemplateFormData(templateConfig.variable_values)
    }
  }, [templateConfig])

  const handleTemplateFormChange = (data: { formData?: Record<string, unknown> }) => {
    if (data.formData) {
      setTemplateFormData(data.formData)
    }
  }

  const handleTemplateDiff = async () => {
    if (!templateConfig?.template_id || !templateFormData) return

    setTemplateDiffLoading(true)
    try {
      await composeQuery.refetch()
      const yaml = await previewMutation.mutateAsync({
        id: templateConfig.template_id,
        variableValues: templateFormData,
      })
      setPreviewYaml(yaml)
      setIsTemplateDiffVisible(true)
    } finally {
      setTemplateDiffLoading(false)
    }
  }

  const handleSubmitTemplateConfig = async () => {
    confirm({
      title: '提交并重建服务器',
      description: '确定要提交配置并重建服务器吗？这将下线当前服务器并使用新配置重新创建。',
      confirmText: '确认重建',
      cancelText: '取消',
      variant: 'destructive',
      onConfirm: async () => {
        const result = await updateTemplateConfigMutation.mutateAsync({
          serverId,
          variableValues: templateFormData,
        })
        setRebuildTaskId(result.task_id)
        setIsRebuildDialogOpen(true)
      },
    })
  }

  const handleResetTemplateForm = () => {
    confirm({
      title: '重新载入配置',
      description: '确定要重新载入配置吗？这将丢失当前表单中的更改。',
      confirmText: '确认',
      cancelText: '取消',
      onConfirm: async () => {
        await refetchTemplateConfig()
        if (templateConfig?.variable_values) {
          setTemplateFormData(templateConfig.variable_values)
        }
        toast.info('配置已重新载入')
      },
    })
  }

  return (
    <div className="flex flex-col h-full gap-4">
      <PageHeader
        title="设置"
        icon={<Settings className="h-5 w-5" />}
        serverTag={serverInfo.name}
        actions={
          <>
            {templateConfig.has_template_update && !templateConfig.template_deleted && (
              <Button
                variant="outline"
                onClick={() => setIsUpdateDialogOpen(true)}
              >
                <RefreshCcw className="mr-1 h-4 w-4" />
                模板有更新
              </Button>
            )}
            <Button
              variant="outline"
              onClick={() => setIsConvertDialogOpen(true)}
            >
              <ArrowLeftRight className="mr-1 h-4 w-4" />
              转换为直接编辑
            </Button>
            <Button
              variant="outline"
              onClick={handleTemplateDiff}
              disabled={templateDiffLoading}
            >
              {templateDiffLoading ? <Spinner className="mr-1 size-4" /> : <GitCompare className="mr-1 h-4 w-4" />}
              差异对比
            </Button>
            <Button
              variant="outline"
              onClick={handleResetTemplateForm}
            >
              <RefreshCw className="mr-1 h-4 w-4" />
              重新载入
            </Button>
            <Button
              variant="destructive"
              onClick={handleSubmitTemplateConfig}
              disabled={updateTemplateConfigMutation.isPending}
            >
              {updateTemplateConfigMutation.isPending ? <Spinner className="mr-1 size-4" /> : <Server className="mr-1 h-4 w-4" />}
              提交并重建
            </Button>
          </>
        }
      />

      <Alert variant={templateConfig.template_deleted ? "destructive" : "default"}>
        <AlertTitle>模板模式</AlertTitle>
        <AlertDescription>
          {templateConfig.template_deleted ? (
            <>
              此服务器使用模板 &quot;{templateConfig.template_name}&quot; 创建，但该模板已被删除。请通过下方表单修改配置，或转换为直接编辑模式。
            </>
          ) : (
            <>
              此服务器使用模板 &quot;<Link to={`/templates/${templateConfig.template_id}/edit`} className="text-blue-600 hover:underline">{templateConfig.template_name}</Link>&quot; 创建，请通过下方表单修改配置。
            </>
          )}
        </AlertDescription>
      </Alert>

      <Card className="flex-1 min-h-0 flex flex-col">
        <CardHeader>
          <CardTitle>配置参数</CardTitle>
        </CardHeader>
        <CardContent className="overflow-y-auto min-h-0">
          <RjsfForm
            schema={templateConfig.json_schema as RJSFSchema}
            uiSchema={templateUiSchema}
            formData={templateFormData}
            validator={validator}
            onChange={handleTemplateFormChange}
            showErrorList={false}
            liveValidate
          >
            <div />
          </RjsfForm>
        </CardContent>
      </Card>

      <ComposeDiffDialog
        open={isTemplateDiffVisible}
        onClose={() => setIsTemplateDiffVisible(false)}
        originalContent={composeContent || ''}
        modifiedContent={previewYaml || ''}
        originalTitle="服务器当前配置"
        modifiedTitle="表单渲染配置"
        description="左侧为服务器当前配置，右侧为根据当前表单参数渲染的配置。高亮显示的是差异部分。"
      />

      <RebuildProgressDialog
        open={isRebuildDialogOpen}
        taskId={rebuildTaskId}
        serverId={serverId}
        onClose={() => {
          setIsRebuildDialogOpen(false)
          setRebuildTaskId(null)
        }}
        onComplete={() => {
          setIsRebuildDialogOpen(false)
          setRebuildTaskId(null)
          refetchTemplateConfig()
          composeQuery.refetch()
        }}
      />

      <ConvertModeDialog
        open={isConvertDialogOpen}
        serverId={serverId}
        currentMode="template"
        onClose={() => setIsConvertDialogOpen(false)}
        onSuccess={onConvertModeSuccess}
      />

      <ConvertModeDialog
        open={isUpdateDialogOpen}
        serverId={serverId}
        currentMode="update"
        initialTemplateId={templateConfig.template_id}
        onClose={() => setIsUpdateDialogOpen(false)}
        onSuccess={onConvertModeSuccess}
      />

      {confirmDialog}
    </div>
  )
}

export default TemplateMode
