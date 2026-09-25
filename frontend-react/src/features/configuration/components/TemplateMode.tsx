import React, { useRef, useState } from 'react'
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

import { Button } from '@/shared/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/shared/ui/card'
import { Alert, AlertTitle, AlertDescription } from '@/shared/ui/alert'
import { Spinner } from '@/shared/ui/spinner'

import RjsfForm from '@/shared/forms/rjsfTheme'
import validator from '@rjsf/validator-ajv8'
import type { RJSFSchema, UiSchema } from '@rjsf/utils'
import { ComposeDiffDialog } from '@/shared/editors/compose/index'
import RebuildProgressDialog from '@/features/configuration/components/RebuildProgressDialog'
import ConvertModeDialog from '@/features/configuration/components/ConvertModeDialog'
import PageHeader from '@/shared/layout/PageHeader'
import { useConfirm } from '@/shared/hooks/useConfirm'
import { useConfigurationSession } from '@/features/configuration/useConfigurationSession'
import { ConfigurationConflict } from '@/features/configuration/components/ConfigurationConflict'
import { useConfigurationCommands } from '@/features/configuration/commands'
import { isConfigurationConflict } from '@/features/configuration/api'
import type { ComposeConfiguration } from '@/features/configuration/contracts'
import type { TemplateConfigResponse } from '@/features/configuration/contracts'

interface ServerInfo {
  name: string
}

interface TemplateModeProps {
  serverId: string
  serverInfo: ServerInfo
  templateConfig: TemplateConfigResponse
  templateReadAt: number
  onConverted: () => void
  composeContent: string
  composeVersion: string
  composeQuery: UseQueryResult<ComposeConfiguration, Error>
  refetchTemplateConfig: UseQueryResult<TemplateConfigResponse>['refetch']
  rebuildTaskId: string | null
  setRebuildTaskId: (id: string | null) => void
  isRebuildDialogOpen: boolean
  setIsRebuildDialogOpen: (visible: boolean) => void
  isConvertDialogOpen: boolean
  setIsConvertDialogOpen: (visible: boolean) => void
}

const TemplateMode: React.FC<TemplateModeProps> = ({
  serverId,
  serverInfo,
  templateConfig,
  templateReadAt,
  onConverted,
  composeContent,
  composeVersion,
  composeQuery,
  refetchTemplateConfig,
  rebuildTaskId,
  setRebuildTaskId,
  isRebuildDialogOpen,
  setIsRebuildDialogOpen,
  isConvertDialogOpen,
  setIsConvertDialogOpen,
}) => {
  const { confirm, confirmDialog } = useConfirm()

  const { updateTemplate: updateTemplateConfigMutation, previewTemplate: previewMutation } = useConfigurationCommands(serverId)
  const snapshot = (config: TemplateConfigResponse, readAt?: number) => ({ version: config.version, value: config, description: JSON.stringify(config, null, 2), readAt })
  const session = useConfigurationSession(snapshot(templateConfig, templateReadAt), true)
  const submittedDraft = useRef<TemplateConfigResponse | null>(null)
  const templateFormData = session.draft.variable_values
  const setTemplateFormData = (variable_values: Record<string, unknown>) => session.setDraft({ ...session.draft, variable_values })
  const refresh = async () => {
    const result = await refetchTemplateConfig({ throwOnError: true })
    if (!result.data?.version) throw new Error('配置版本缺失')
    return snapshot(result.data, result.dataUpdatedAt)
  }
  const handleFailure = (code?: string) => {
    if (code === 'configuration_conflict') { session.markConflict(); void refresh().catch(() => undefined) }
  }
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

  const handleTemplateFormChange = (data: { formData?: Record<string, unknown> }) => {
    if (data.formData) {
      setTemplateFormData(data.formData)
    }
  }

  const handleTemplateDiff = async () => {
    if (!templateConfig?.template_id || !templateFormData) return

    setTemplateDiffLoading(true)
    try {
      await composeQuery.refetch({ throwOnError: true })
      const yaml = await previewMutation.mutateAsync(templateFormData)
      setPreviewYaml(yaml)
      setIsTemplateDiffVisible(true)
    } catch {
      toast.error('获取配置差异失败，已保留表单内容')
    } finally {
      setTemplateDiffLoading(false)
    }
  }

  const handleSubmitTemplateConfig = async () => {
    try {
      const latest = await refresh()
      if (latest.version !== session.baseline.version || !session.canSubmit) { session.markConflict(); return }
    } catch { toast.error('获取最新配置失败，已保留表单内容，请重试'); return }
    confirm({
      title: '提交并重建服务器',
      description: '确定要提交配置并重建服务器吗？这将下线当前服务器并使用新配置重新创建。',
      confirmText: '确认重建',
      cancelText: '取消',
      variant: 'destructive',
      onConfirm: async () => {
        try {
          submittedDraft.current = { ...session.baseline.value, variable_values: templateFormData }
          const result = await updateTemplateConfigMutation.mutateAsync({
            value: templateFormData,
            version: session.baseline.version,
          })
          setRebuildTaskId(result.task_id)
          setIsRebuildDialogOpen(true)
        } catch (error) {
          if (isConfigurationConflict(error)) handleFailure('configuration_conflict')
        }
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
        try {
          session.reset(await refresh())
          toast.info('配置已重新载入')
        } catch {
          toast.error('重新载入失败，已保留表单内容')
        }
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
              disabled={updateTemplateConfigMutation.isPending || !session.canSubmit}
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

      <ConfigurationConflict {...session} needed={session.needsComparison} draftDescription={JSON.stringify({ ...session.baseline.value, variable_values: templateFormData }, null, 2)} refresh={refresh} />

      <Card className="flex-1 min-h-0 flex flex-col">
        <CardHeader>
          <CardTitle>配置参数</CardTitle>
        </CardHeader>
        <CardContent className="overflow-y-auto min-h-0">
          <RjsfForm
            schema={session.baseline.value.json_schema as RJSFSchema}
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
        onFailure={handleFailure}
        onClose={() => {
          setIsRebuildDialogOpen(false)
          setRebuildTaskId(null)
        }}
        onComplete={result => {
          if (typeof result?.version === 'string' && submittedDraft.current) session.markApplied(snapshot({ ...submittedDraft.current, version: result.version }))
          submittedDraft.current = null
          setIsRebuildDialogOpen(false)
          setRebuildTaskId(null)
        }}
      />

      <ConvertModeDialog
        open={isConvertDialogOpen}
        serverId={serverId}
        currentMode="template"
        onClose={() => setIsConvertDialogOpen(false)}
        initialVersion={composeVersion}
        onSuccess={onConverted}
      />

      <ConvertModeDialog
        open={isUpdateDialogOpen}
        serverId={serverId}
        currentMode="update"
        initialTemplateId={templateConfig.template_id}
        onClose={() => setIsUpdateDialogOpen(false)}
        initialVersion={composeVersion}
        onSuccess={() => setIsUpdateDialogOpen(false)}
      />

      {confirmDialog}
    </div>
  )
}

export default TemplateMode
