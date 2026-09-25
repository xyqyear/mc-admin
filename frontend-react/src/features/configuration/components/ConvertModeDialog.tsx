import React, { useState, useEffect } from 'react'
import { toast } from 'sonner'
import { Check, ArrowLeftRight, RefreshCw } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { composeOptions } from '@/features/configuration/queries'
import { useConfigurationCommands } from '@/features/configuration/commands'
import { useConfigurationSession } from '@/features/configuration/useConfigurationSession'
import { ConfigurationConflict } from '@/features/configuration/components/ConfigurationConflict'
import { isConfigurationConflict } from '@/features/configuration/api'

import { Button } from '@/shared/ui/button'
import { Alert, AlertTitle, AlertDescription } from '@/shared/ui/alert'
import { Spinner } from '@/shared/ui/spinner'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/shared/ui/dialog'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/shared/ui/select'

import { MonacoDiffEditor } from '@/shared/editors/index'
import RjsfForm from '@/shared/forms/rjsfTheme'
import validator from '@rjsf/validator-ajv8'
import type { RJSFSchema } from '@rjsf/utils'
import { useTemplates } from '@/features/templates/queries'
import { useTemplateMutations } from '@/features/templates/commands'
import type { ExtractVariablesResponse } from '@/features/configuration/contracts'
import RebuildProgressDialog from '@/features/configuration/components/RebuildProgressDialog'
import { cn } from '@/shared/lib/utils'

interface ConvertModeDialogProps {
  open: boolean
  serverId: string
  currentMode: 'template' | 'direct' | 'update'
  initialTemplateId?: number
  onClose: () => void
  initialVersion: string
  onSuccess: () => void
}

const StepIndicator = ({ steps, currentStep }: { steps: string[]; currentStep: number }) => (
  <div className="flex items-center mb-6">
    {steps.map((title, i) => (
      <React.Fragment key={i}>
        {i > 0 && (
          <div className={cn('flex-1 h-px mx-2', i <= currentStep ? 'bg-primary' : 'bg-border')} />
        )}
        <div className="flex flex-col items-center gap-1">
          <div className={cn(
            'flex h-7 w-7 items-center justify-center rounded-full text-xs font-medium',
            i < currentStep && 'bg-primary text-primary-foreground',
            i === currentStep && 'border-2 border-primary text-primary',
            i > currentStep && 'border-2 border-muted-foreground/25 text-muted-foreground'
          )}>
            {i < currentStep ? <Check className="h-3.5 w-3.5" /> : i + 1}
          </div>
          <span className={cn('text-xs', i <= currentStep ? 'text-foreground' : 'text-muted-foreground')}>
            {title}
          </span>
        </div>
      </React.Fragment>
    ))}
  </div>
)

const ConvertModeEditor: React.FC<ConvertModeDialogProps> = ({
  open,
  serverId,
  currentMode,
  initialTemplateId,
  onClose,
  initialVersion,
  onSuccess,
}) => {
  const [currentStep, setCurrentStep] = useState(0)
  const [selectedTemplateId, setSelectedTemplateId] = useState<number | null>(null)
  const [extractResult, setExtractResult] = useState<ExtractVariablesResponse | null>(null)
  const [formData, setFormData] = useState<Record<string, unknown>>({})
  const [rebuildTaskId, setRebuildTaskId] = useState<string | null>(null)
  const [isRebuildDialogOpen, setIsRebuildDialogOpen] = useState(false)
  const [previewYaml, setPreviewYaml] = useState<string>('')
  const [previewLoading, setPreviewLoading] = useState(false)
  const [requiresRebuild, setRequiresRebuild] = useState<boolean | null>(null)

  const { data: templates, isLoading: templatesLoading } = useTemplates()
  const composeQuery = useQuery(composeOptions(serverId))
  const yaml = composeQuery.data?.yaml_content ?? ''
  const session = useConfigurationSession({ version: composeQuery.data?.version ?? initialVersion, value: yaml, description: yaml })
  const {
    convertToDirect: convertToDirectMutation,
    extractVariables: extractVariablesMutation,
    convertToTemplate: convertToTemplateMutation,
    checkConversion: checkConversionMutation,
  } = useConfigurationCommands(serverId)
  const { usePreviewRenderedYaml } = useTemplateMutations()
  const previewRenderedYamlMutation = usePreviewRenderedYaml()
  const refresh = async () => {
    const result = await composeQuery.refetch({ throwOnError: true })
    if (!result.data?.version) throw new Error('配置版本缺失')
    return { version: result.data.version, value: result.data.yaml_content, description: result.data.yaml_content }
  }
  const handleFailure = (code?: string) => {
    if (code === 'configuration_conflict') { session.markConflict(); void refresh().catch(() => undefined) }
  }
  const conflictPanel = <ConfigurationConflict {...session} needed={session.needsComparison}
    draftDescription={previewYaml || session.draft} refresh={refresh}
    accept={snapshot => { session.accept(snapshot); if (currentMode !== 'template') { setRequiresRebuild(null); setCurrentStep(1) } }} />

  useEffect(() => {
    if (open) {
      setCurrentStep(0)
      setSelectedTemplateId(currentMode === 'update' && initialTemplateId ? initialTemplateId : null)
      setExtractResult(null)
      setFormData({})
      setPreviewYaml('')
      setRequiresRebuild(null)
    }
  }, [open, currentMode, initialTemplateId])

  useEffect(() => {
    if (extractResult) {
      setFormData(extractResult.extracted_values)
    }
  }, [extractResult])

  const handleConvertToDirect = async () => {
    if (!session.canSubmit) return
    try {
      await convertToDirectMutation.mutateAsync(session.baseline.version)
      onSuccess()
      onClose()
    } catch (error) {
      if (isConfigurationConflict(error)) handleFailure('configuration_conflict')
    }
  }

  const handleExtractVariables = async () => {
    if (!selectedTemplateId) return
    try {
      const result = await extractVariablesMutation.mutateAsync(selectedTemplateId)
      setExtractResult(result)
      setCurrentStep(1)
      if (result.version !== session.baseline.version) handleFailure('configuration_conflict')
    } catch { /* The mutation reports read errors without discarding the form. */ }
  }

  const handleGoToPreview = async () => {
    if (!selectedTemplateId) return
    setPreviewLoading(true)
    try {
      const [rendered, checkResult] = await Promise.all([
        previewRenderedYamlMutation.mutateAsync({
          id: selectedTemplateId,
          variableValues: formData,
        }),
        checkConversionMutation.mutateAsync({
          templateId: selectedTemplateId,
          value: formData,
        }),
      ])
      setPreviewYaml(rendered)
      setRequiresRebuild(checkResult.requires_rebuild)
      if (checkResult.version !== session.baseline.version) handleFailure('configuration_conflict')
      setCurrentStep(2)
    } catch {
      // Mutation hooks surface the errors.
    } finally {
      setPreviewLoading(false)
    }
  }

  const handleConvertToTemplate = async () => {
    if (!selectedTemplateId || !session.canSubmit) return
    try {
      const result = await convertToTemplateMutation.mutateAsync({
        templateId: selectedTemplateId, value: formData, version: session.baseline.version,
      })
      if (result.skipped_rebuild) { toast.success('配置已更新'); onSuccess(); onClose() }
      else { setRebuildTaskId(result.task_id!); setIsRebuildDialogOpen(true) }
    } catch (error) {
      if (isConfigurationConflict(error)) handleFailure('configuration_conflict')
    }
  }

  const handleRebuildComplete = () => {
    setIsRebuildDialogOpen(false)
    setRebuildTaskId(null)
    onSuccess()
    onClose()
  }

  const isUpdateMode = currentMode === 'update'
  const isWizardMode = currentMode === 'direct' || currentMode === 'update'

  if (currentMode === 'template') {
    return (
      <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <ArrowLeftRight className="h-5 w-5" />
              转换为直接编辑模式
            </DialogTitle>
          </DialogHeader>
          {conflictPanel}
          <div className="space-y-4">
            <Alert variant="destructive">
              <AlertTitle>确认转换</AlertTitle>
              <AlertDescription>转换后，您将可以直接编辑 Docker Compose 文件。模板关联将被解除，但当前配置不会改变。</AlertDescription>
            </Alert>
            <p className="text-sm">此操作不会重建服务器，仅解除模板关联。</p>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={onClose}>取消</Button>
            <Button
              variant="destructive"
              onClick={handleConvertToDirect}
              disabled={convertToDirectMutation.isPending || !session.canSubmit}
            >
              {convertToDirectMutation.isPending && <Spinner className="mr-2 size-4" />}
              确认转换
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    )
  }

  if (!isWizardMode) return null

  const steps = ['选择模板', '调整变量', '确认差异']

  const renderStepContent = () => {
    if (currentStep === 0) {
      return (
        <div className="space-y-4">
          <Alert>
            <AlertTitle>{isUpdateMode ? "检查模板更新" : "选择目标模板"}</AlertTitle>
            <AlertDescription>
              {isUpdateMode
                ? "系统将从当前配置中提取变量值，并与最新模板进行匹配。"
                : "系统将尝试从当前 Compose 文件中提取变量值。"
              }
            </AlertDescription>
          </Alert>
          <Select
            value={selectedTemplateId ? String(selectedTemplateId) : undefined}
            onValueChange={(v) => setSelectedTemplateId(Number(v))}
            disabled={isUpdateMode}
            itemToStringLabel={(v) => templates?.find(t => String(t.id) === v)?.name ?? v}
          >
            <SelectTrigger className="w-full">
              <SelectValue placeholder="选择模板" />
            </SelectTrigger>
            <SelectContent>
              {templatesLoading ? (
                <div className="flex justify-center py-4">
                  <Spinner className="size-4" />
                </div>
              ) : (
                templates?.map(t => (
                  <SelectItem key={t.id} value={String(t.id)}>{t.name}</SelectItem>
                ))
              )}
            </SelectContent>
          </Select>
        </div>
      )
    }

    if (currentStep === 1 && extractResult) {
      return (
        <div className="space-y-4">
          {extractResult.warnings.length > 0 && (
            <Alert variant="destructive">
              <AlertTitle>提取警告</AlertTitle>
              <AlertDescription>
                <ul className="list-disc pl-4 mb-0">
                  {extractResult.warnings.map((w, i) => <li key={i}>{w}</li>)}
                </ul>
              </AlertDescription>
            </Alert>
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
          <Alert variant={requiresRebuild === null ? 'default' : requiresRebuild ? 'destructive' : 'default'}>
            <AlertTitle>确认配置差异</AlertTitle>
            <AlertDescription>
              {requiresRebuild === null
                ? "正在检查配置差异..."
                : requiresRebuild
                ? "检测到配置差异，确认后将重建服务器。"
                : "配置无变化，确认后将直接更新模板关联，不会重建服务器。"
              }
            </AlertDescription>
          </Alert>
          <div className="border rounded-md overflow-hidden h-125">
            <MonacoDiffEditor
              language="yaml"
              original={session.remote.description}
              modified={previewYaml}
              originalTitle="当前配置"
              modifiedTitle="模板渲染结果"
              options={{ minimap: { enabled: false }, readOnly: true }}
            />
          </div>
        </div>
      )
    }

    return (
      <div className="flex justify-center py-8">
        <Spinner className="size-8" />
      </div>
    )
  }

  return (
    <>
      <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
        <DialogContent className={cn(currentStep === 2 ? 'sm:max-w-250' : 'sm:max-w-lg')}>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              {isUpdateMode ? <RefreshCw className="h-5 w-5" /> : <ArrowLeftRight className="h-5 w-5" />}
              {isUpdateMode ? '更新模板配置' : '转换为模板模式'}
            </DialogTitle>
          </DialogHeader>

          {conflictPanel}
          <StepIndicator steps={steps} currentStep={currentStep} />
          {renderStepContent()}

          <DialogFooter>
            <Button variant="outline" onClick={onClose}>取消</Button>
            {currentStep === 0 && (
              <Button
                onClick={handleExtractVariables}
                disabled={!selectedTemplateId || extractVariablesMutation.isPending}
              >
                {extractVariablesMutation.isPending && <Spinner className="mr-2 size-4" />}
                下一步
              </Button>
            )}
            {currentStep === 1 && (
              <>
                <Button variant="outline" onClick={() => setCurrentStep(0)}>上一步</Button>
                <Button
                  onClick={handleGoToPreview}
                  disabled={previewLoading}
                >
                  {previewLoading && <Spinner className="mr-2 size-4" />}
                  下一步
                </Button>
              </>
            )}
            {currentStep === 2 && (
              <>
                <Button variant="outline" onClick={() => setCurrentStep(1)}>上一步</Button>
                <Button
                  variant={requiresRebuild === true ? 'destructive' : 'default'}
                  onClick={handleConvertToTemplate}
                  disabled={convertToTemplateMutation.isPending || requiresRebuild === null || !session.canSubmit}
                >
                  {convertToTemplateMutation.isPending && <Spinner className="mr-2 size-4" />}
                  {requiresRebuild === null
                    ? "检查中..."
                    : requiresRebuild
                    ? (isUpdateMode ? '确认更新并重建' : '确认并重建')
                    : "确认"}
                </Button>
              </>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <RebuildProgressDialog
        open={isRebuildDialogOpen}
        taskId={rebuildTaskId}
        onFailure={handleFailure}
        onClose={() => setIsRebuildDialogOpen(false)}
        onComplete={handleRebuildComplete}
      />
    </>
  )
}

export default function ConvertModeDialog(props: ConvertModeDialogProps) {
  return props.open ? <ConvertModeEditor key={`${props.serverId}:${props.currentMode}`} {...props} /> : null
}
