import React, { useState, useEffect } from 'react'
import { Card, Button, Alert, App } from 'antd'
import {
  ReloadOutlined,
  ExclamationCircleOutlined,
  CloudServerOutlined,
  DiffOutlined,
  SwapOutlined,
  SyncOutlined,
} from '@ant-design/icons'
import { Link } from 'react-router-dom'
import type { UseQueryResult } from '@tanstack/react-query'
import RjsfForm from '@/components/forms/rjsfTheme'
import validator from '@rjsf/validator-ajv8'
import type { RJSFSchema, UiSchema } from '@rjsf/utils'
import { ComposeDiffModal } from '@/components/modals/ServerCompose'
import RebuildProgressModal from '@/components/modals/RebuildProgressModal'
import ConvertModeModal from '@/components/modals/ConvertModeModal'
import PageHeader from '@/components/layout/PageHeader'
import { SettingOutlined } from '@ant-design/icons'
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
  isRebuildModalVisible: boolean
  setIsRebuildModalVisible: (visible: boolean) => void
  isConvertModalVisible: boolean
  setIsConvertModalVisible: (visible: boolean) => void
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
  isRebuildModalVisible,
  setIsRebuildModalVisible,
  isConvertModalVisible,
  setIsConvertModalVisible,
  onConvertModeSuccess,
}) => {
  const { modal, message } = App.useApp()

  const { useUpdateServerTemplateConfig, usePreviewRenderedYaml } = useTemplateMutations()
  const updateTemplateConfigMutation = useUpdateServerTemplateConfig()
  const previewMutation = usePreviewRenderedYaml()

  const [templateFormData, setTemplateFormData] = useState<Record<string, unknown>>({})
  const [previewYaml, setPreviewYaml] = useState<string | null>(null)
  const [isTemplateDiffVisible, setIsTemplateDiffVisible] = useState(false)
  const [templateDiffLoading, setTemplateDiffLoading] = useState(false)
  const [isUpdateModalVisible, setIsUpdateModalVisible] = useState(false)

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
    modal.confirm({
      title: '提交并重建服务器',
      content: '确定要提交配置并重建服务器吗？这将下线当前服务器并使用新配置重新创建。',
      okText: '确认重建',
      okType: 'danger',
      cancelText: '取消',
      icon: <ExclamationCircleOutlined />,
      onOk: async () => {
        const result = await updateTemplateConfigMutation.mutateAsync({
          serverId,
          variableValues: templateFormData,
        })
        setRebuildTaskId(result.task_id)
        setIsRebuildModalVisible(true)
      }
    })
  }

  const handleResetTemplateForm = () => {
    modal.confirm({
      title: '重新载入配置',
      content: '确定要重新载入配置吗？这将丢失当前表单中的更改。',
      okText: '确认',
      cancelText: '取消',
      icon: <ExclamationCircleOutlined />,
      onOk: async () => {
        await refetchTemplateConfig()
        if (templateConfig?.variable_values) {
          setTemplateFormData(templateConfig.variable_values)
        }
        message.info('配置已重新载入')
      }
    })
  }

  return (
    <div className="flex flex-col h-full gap-4">
      <PageHeader
        title="设置"
        icon={<SettingOutlined />}
        serverTag={serverInfo.name}
        actions={
          <>
            {templateConfig.has_template_update && !templateConfig.template_deleted && (
              <Button
                type="primary"
                ghost
                icon={<SyncOutlined />}
                onClick={() => setIsUpdateModalVisible(true)}
              >
                模板有更新
              </Button>
            )}
            <Button
              icon={<SwapOutlined />}
              onClick={() => setIsConvertModalVisible(true)}
            >
              转换为直接编辑
            </Button>
            <Button
              icon={<DiffOutlined />}
              onClick={handleTemplateDiff}
              loading={templateDiffLoading}
            >
              差异对比
            </Button>
            <Button
              icon={<ReloadOutlined />}
              onClick={handleResetTemplateForm}
            >
              重新载入
            </Button>
            <Button
              type="primary"
              danger
              icon={<CloudServerOutlined />}
              onClick={handleSubmitTemplateConfig}
              loading={updateTemplateConfigMutation.isPending}
            >
              提交并重建
            </Button>
          </>
        }
      />

      <Alert
        title="模板模式"
        description={
          templateConfig.template_deleted ? (
            <>
              此服务器使用模板 &quot;{templateConfig.template_name}&quot; 创建，但该模板已被删除。请通过下方表单修改配置，或转换为直接编辑模式。
            </>
          ) : (
            <>
              此服务器使用模板 &quot;<Link to={`/templates/${templateConfig.template_id}/edit`}>{templateConfig.template_name}</Link>&quot; 创建，请通过下方表单修改配置。
            </>
          )
        }
        type={templateConfig.template_deleted ? "warning" : "info"}
        showIcon
      />

      <Card className="flex-1" title="配置参数">
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
      </Card>

      <ComposeDiffModal
        open={isTemplateDiffVisible}
        onClose={() => setIsTemplateDiffVisible(false)}
        originalContent={composeContent || ''}
        modifiedContent={previewYaml || ''}
        originalTitle="服务器当前配置"
        modifiedTitle="表单渲染配置"
        description="左侧为服务器当前配置，右侧为根据当前表单参数渲染的配置。高亮显示的是差异部分。"
      />

      <RebuildProgressModal
        open={isRebuildModalVisible}
        taskId={rebuildTaskId}
        serverId={serverId}
        onClose={() => {
          setIsRebuildModalVisible(false)
          setRebuildTaskId(null)
        }}
        onComplete={() => {
          setIsRebuildModalVisible(false)
          setRebuildTaskId(null)
          refetchTemplateConfig()
          composeQuery.refetch()
        }}
      />

      <ConvertModeModal
        open={isConvertModalVisible}
        serverId={serverId}
        currentMode="template"
        onClose={() => setIsConvertModalVisible(false)}
        onSuccess={onConvertModeSuccess}
      />

      <ConvertModeModal
        open={isUpdateModalVisible}
        serverId={serverId}
        currentMode="update"
        initialTemplateId={templateConfig.template_id}
        onClose={() => setIsUpdateModalVisible(false)}
        onSuccess={onConvertModeSuccess}
      />
    </div>
  )
}

export default TemplateMode
