import React, { useState, useEffect } from 'react'
import { Modal, Steps, Select, Alert, Button, Space, Spin } from 'antd'
import { ExclamationCircleOutlined, SwapOutlined, SyncOutlined } from '@ant-design/icons'
import { useQueryClient } from '@tanstack/react-query'
import { MonacoDiffEditor } from '@/components/editors'
import RjsfForm from '@/components/forms/rjsfTheme'
import validator from '@rjsf/validator-ajv8'
import type { RJSFSchema } from '@rjsf/utils'
import { useTemplates } from '@/hooks/queries/base/useTemplateQueries'
import { useTemplateMutations } from '@/hooks/mutations/useTemplateMutations'
import { templateApi, ExtractVariablesResponse } from '@/hooks/api/templateApi'
import { queryKeys } from '@/utils/api'
import RebuildProgressModal from './RebuildProgressModal'

interface ConvertModeModalProps {
  open: boolean
  serverId: string
  currentMode: 'template' | 'direct' | 'update'
  initialTemplateId?: number
  onClose: () => void
  onSuccess: () => void
}

const ConvertModeModal: React.FC<ConvertModeModalProps> = ({
  open,
  serverId,
  currentMode,
  initialTemplateId,
  onClose,
  onSuccess,
}) => {
  const [currentStep, setCurrentStep] = useState(0)
  const [selectedTemplateId, setSelectedTemplateId] = useState<number | null>(null)
  const [extractResult, setExtractResult] = useState<ExtractVariablesResponse | null>(null)
  const [formData, setFormData] = useState<Record<string, unknown>>({})
  const [rebuildTaskId, setRebuildTaskId] = useState<string | null>(null)
  const [isRebuildModalVisible, setIsRebuildModalVisible] = useState(false)
  const [previewYaml, setPreviewYaml] = useState<string>('')
  const [previewLoading, setPreviewLoading] = useState(false)

  const { data: templates, isLoading: templatesLoading } = useTemplates()
  const queryClient = useQueryClient()
  const {
    useConvertToDirectMode,
    useExtractVariables,
    useConvertToTemplateMode,
  } = useTemplateMutations()

  const convertToDirectMutation = useConvertToDirectMode()
  const extractVariablesMutation = useExtractVariables()
  const convertToTemplateMutation = useConvertToTemplateMode()

  // Reset state when modal opens/closes
  useEffect(() => {
    if (open) {
      setCurrentStep(0)
      setSelectedTemplateId(currentMode === 'update' && initialTemplateId ? initialTemplateId : null)
      setExtractResult(null)
      setFormData({})
      setPreviewYaml('')
    }
  }, [open, currentMode, initialTemplateId])

  // Update form data when extract result changes
  useEffect(() => {
    if (extractResult) {
      setFormData(extractResult.extracted_values)
    }
  }, [extractResult])

  const handleConvertToDirect = async () => {
    await convertToDirectMutation.mutateAsync(serverId)
    onSuccess()
    onClose()
  }

  const handleExtractVariables = async () => {
    if (!selectedTemplateId) return
    const result = await extractVariablesMutation.mutateAsync({
      serverId,
      templateId: selectedTemplateId,
    })
    setExtractResult(result)
    setCurrentStep(1)
  }

  const handleGoToPreview = async () => {
    if (!selectedTemplateId) return
    setPreviewLoading(true)
    try {
      const rendered = await templateApi.previewRenderedYaml(selectedTemplateId, formData)
      setPreviewYaml(rendered)
      setCurrentStep(2)
    } finally {
      setPreviewLoading(false)
    }
  }

  const handleConvertToTemplate = async () => {
    if (!selectedTemplateId) return
    const result = await convertToTemplateMutation.mutateAsync({
      serverId,
      templateId: selectedTemplateId,
      variableValues: formData,
    })
    setRebuildTaskId(result.task_id)
    setIsRebuildModalVisible(true)
  }

  const handleRebuildComplete = () => {
    setIsRebuildModalVisible(false)
    setRebuildTaskId(null)
    // Invalidate serverConfigPreview to refresh template mode status
    queryClient.invalidateQueries({
      queryKey: queryKeys.templates.serverConfigPreview(serverId),
    })
    queryClient.invalidateQueries({
      queryKey: queryKeys.templates.serverConfig(serverId),
    })
    onSuccess()
    onClose()
  }

  const isUpdateMode = currentMode === 'update'
  const isWizardMode = currentMode === 'direct' || currentMode === 'update'

  // Template -> Direct: Simple confirmation
  if (currentMode === 'template') {
    return (
      <Modal
        title={<><SwapOutlined /> 转换为直接编辑模式</>}
        open={open}
        onCancel={onClose}
        onOk={handleConvertToDirect}
        okText="确认转换"
        okType="danger"
        confirmLoading={convertToDirectMutation.isPending}
      >
        <Alert
          title="确认转换"
          description="转换后，您将可以直接编辑 Docker Compose 文件。模板关联将被解除，但当前配置不会改变。"
          type="warning"
          showIcon
          icon={<ExclamationCircleOutlined />}
          className="mb-4"
        />
        <p>此操作不会重建服务器，仅解除模板关联。</p>
      </Modal>
    )
  }

  // Direct -> Template / Update: Multi-step wizard
  if (!isWizardMode) return null
  const steps = [
    { title: '选择模板' },
    { title: '调整变量' },
    { title: '确认差异' },
  ]

  const getModalWidth = () => {
    if (currentStep === 2) return 1000
    return 520
  }

  const renderStepContent = () => {
    if (currentStep === 0) {
      return (
        <div className="space-y-4">
          <Alert
            title={isUpdateMode ? "检查模板更新" : "选择目标模板"}
            description={isUpdateMode
              ? "系统将从当前配置中提取变量值，并与最新模板进行匹配。"
              : "系统将尝试从当前 Compose 文件中提取变量值。"
            }
            type="info"
            showIcon
          />
          <Select
            placeholder="选择模板"
            className="w-full"
            loading={templatesLoading}
            value={selectedTemplateId}
            onChange={setSelectedTemplateId}
            disabled={isUpdateMode}
            options={templates?.map(t => ({ label: t.name, value: t.id }))}
          />
        </div>
      )
    }

    if (currentStep === 1 && extractResult) {
      return (
        <div className="space-y-4">
          {extractResult.warnings.length > 0 && (
            <Alert
              title="提取警告"
              description={
                <ul className="list-disc pl-4 mb-0">
                  {extractResult.warnings.map((w, i) => <li key={i}>{w}</li>)}
                </ul>
              }
              type="warning"
              showIcon
            />
          )}
          <RjsfForm
            schema={extractResult.json_schema as RJSFSchema}
            formData={formData}
            validator={validator}
            onChange={({ formData: data }) => data && setFormData(data)}
            showErrorList={false}
            liveValidate
          >
            <div />
          </RjsfForm>
        </div>
      )
    }

    if (currentStep === 2 && extractResult) {
      return (
        <div className="space-y-4">
          <Alert
            title="确认配置差异"
            description="请检查当前配置与模板渲染结果的差异，确认无误后点击「确认并重建」。"
            type="info"
            showIcon
          />
          <div className="border rounded overflow-hidden" style={{ height: 500 }}>
            <MonacoDiffEditor
              language="yaml"
              original={extractResult.current_compose}
              modified={previewYaml}
              originalTitle="当前配置"
              modifiedTitle="模板渲染结果"
              options={{ minimap: { enabled: false }, readOnly: true }}
            />
          </div>
        </div>
      )
    }

    return <Spin />
  }

  const renderFooter = () => {
    return (
      <Space>
        <Button onClick={onClose}>取消</Button>
        {currentStep === 0 && (
          <Button
            type="primary"
            onClick={handleExtractVariables}
            disabled={!selectedTemplateId}
            loading={extractVariablesMutation.isPending}
          >
            下一步
          </Button>
        )}
        {currentStep === 1 && (
          <>
            <Button onClick={() => setCurrentStep(0)}>上一步</Button>
            <Button
              type="primary"
              onClick={handleGoToPreview}
              loading={previewLoading}
            >
              下一步
            </Button>
          </>
        )}
        {currentStep === 2 && (
          <>
            <Button onClick={() => setCurrentStep(1)}>上一步</Button>
            <Button
              type="primary"
              danger
              onClick={handleConvertToTemplate}
              loading={convertToTemplateMutation.isPending}
            >
              {isUpdateMode ? '确认更新并重建' : '确认并重建'}
            </Button>
          </>
        )}
      </Space>
    )
  }

  return (
    <>
      <Modal
        title={isUpdateMode ? <><SyncOutlined /> 更新模板配置</> : <><SwapOutlined /> 转换为模板模式</>}
        open={open}
        onCancel={onClose}
        width={getModalWidth()}
        footer={renderFooter()}
      >
        <Steps current={currentStep} items={steps} className="mb-6" />
        {renderStepContent()}
      </Modal>

      <RebuildProgressModal
        open={isRebuildModalVisible}
        taskId={rebuildTaskId}
        serverId={serverId}
        onClose={() => setIsRebuildModalVisible(false)}
        onComplete={handleRebuildComplete}
      />
    </>
  )
}

export default ConvertModeModal
