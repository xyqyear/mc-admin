import React, { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { toast } from 'sonner'
import {
  Settings,
  GitCompareArrows,
  Save,
  Undo2,
  Loader2,
  Info,
} from 'lucide-react'

import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Alert, AlertTitle, AlertDescription } from '@/components/ui/alert'
import { Separator } from '@/components/ui/separator'
import { Spinner } from '@/components/ui/spinner'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'

import Form from '@/components/forms/rjsfTheme'
import validator from '@rjsf/validator-ajv8'
import { MonacoDiffEditor } from '@/components/editors'
import LoadingSpinner from '@/components/layout/LoadingSpinner'
import PageHeader from '@/components/layout/PageHeader'
import { RefreshButton } from '@/components/common/RefreshButton'
import { useConfigModules, useModuleConfig, useModuleSchema } from '@/hooks/queries/base/useConfigQueries'
import { useUpdateModuleConfig, useResetModuleConfig } from '@/hooks/mutations/useConfigMutations'
import { useConfirm } from '@/hooks/useConfirm'
import type { RJSFSchema } from '@rjsf/utils'

const DynamicConfig: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams()
  const selectedModule = searchParams.get('module')
  const [formData, setFormData] = useState<any>({})
  const [isCompareVisible, setIsCompareVisible] = useState(false)
  const [submitDialogData, setSubmitDialogData] = useState<{
    hasChanges: boolean
    latestConfigData: any
  } | null>(null)

  const { confirm, confirmDialog } = useConfirm()

  const { data: modules, isLoading: modulesLoading, error: modulesError } = useConfigModules()
  const {
    data: moduleConfig,
    isLoading: configLoading,
    isFetching: configFetching,
    error: configError,
    refetch: refetchConfig,
  } = useModuleConfig(selectedModule)
  const {
    data: moduleSchema,
    isLoading: schemaLoading,
    isFetching: schemaFetching,
    error: schemaError,
  } = useModuleSchema(selectedModule)

  const updateConfigMutation = useUpdateModuleConfig()
  const resetConfigMutation = useResetModuleConfig()

  useEffect(() => {
    if (moduleConfig?.config_data) {
      setFormData(moduleConfig.config_data)
    }
  }, [moduleConfig])

  const handleModuleChange = (moduleName: string | null) => {
    if (!moduleName) return
    setFormData({})
    setSearchParams({ module: moduleName })
  }

  const handleFormChange = ({ formData: newFormData }: any) => {
    setFormData(newFormData)
  }

  const handleReloadConfig = () => {
    confirm({
      title: '重新载入配置',
      description: '确定要重新载入配置吗？这将丢失当前表单中的更改，恢复到服务器的配置。',
      confirmText: '确认',
      cancelText: '取消',
      onConfirm: async () => {
        try {
          const refreshedConfig = await refetchConfig()
          if (refreshedConfig.data?.config_data) {
            setFormData(refreshedConfig.data.config_data)
          }
          toast.info('配置已重新载入')
        } catch (error: any) {
          toast.error(`重新载入失败: ${error.message}`)
        }
      },
    })
  }

  const handleResetToDefaults = () => {
    if (!selectedModule) return
    confirm({
      title: '重置为默认配置',
      description: '确定要将配置重置为默认值吗？这将覆盖所有当前设置。',
      confirmText: '确认重置',
      cancelText: '取消',
      variant: 'destructive',
      onConfirm: async () => {
        try {
          const result = await resetConfigMutation.mutateAsync(selectedModule)
          if (result.updated_config) {
            setFormData(result.updated_config)
          }
        } catch {
          // Error toast handled by mutation's onError
        }
      },
    })
  }

  const handleSubmitConfig = async () => {
    if (!selectedModule || !moduleConfig) return

    const toastId = toast.loading('正在获取最新配置...')
    let latestConfig = moduleConfig

    try {
      const refreshedConfig = await refetchConfig()
      if (refreshedConfig.data) {
        latestConfig = refreshedConfig.data
      }
    } catch {
      toast.warning('获取最新配置失败，将使用当前缓存的配置进行对比')
    } finally {
      toast.dismiss(toastId)
    }

    const hasChanges = JSON.stringify(formData) !== JSON.stringify(latestConfig.config_data)
    setSubmitDialogData({ hasChanges, latestConfigData: latestConfig.config_data })
  }

  const handleConfirmSubmit = async () => {
    if (!selectedModule) return
    try {
      await updateConfigMutation.mutateAsync({
        moduleName: selectedModule,
        configData: formData,
      })
      setSubmitDialogData(null)
    } catch {
      // Error toast handled by mutation's onError
    }
  }

  const handleCompareConfig = async () => {
    const toastId = toast.loading('正在获取最新配置...')
    try {
      await refetchConfig()
      setIsCompareVisible(true)
    } catch {
      toast.warning('获取最新配置失败，使用当前缓存的配置进行对比')
      setIsCompareVisible(true)
    } finally {
      toast.dismiss(toastId)
    }
  }

  if (modulesLoading) {
    return <LoadingSpinner height="16rem" />
  }

  if (modulesError) {
    return (
      <div className="flex justify-center items-center min-h-64">
        <Alert variant="destructive">
          <AlertTitle>加载失败</AlertTitle>
          <AlertDescription>无法加载动态配置模块</AlertDescription>
        </Alert>
      </div>
    )
  }

  const moduleOptions = Object.entries(modules?.modules || {}).map(([key, module]) => ({
    label: `${module.module_name} (${module.schema_class})`,
    value: key,
  }))

  const isConfigLoaded = moduleConfig && moduleSchema && !configLoading && !schemaLoading

  return (
    <div className="space-y-4">
      <PageHeader
        title="动态配置管理"
        icon={<Settings className="h-5 w-5" />}
        actions={
          selectedModule && isConfigLoaded ? (
            <>
              <Button variant="outline" onClick={handleCompareConfig}>
                <GitCompareArrows className="mr-2 h-4 w-4" />
                差异对比
              </Button>
              <RefreshButton
                onClick={handleReloadConfig}
                isRefreshing={configFetching || schemaFetching}
                label="重新载入"
              />
              <Button
                variant="destructive"
                onClick={handleResetToDefaults}
                disabled={resetConfigMutation.isPending}
              >
                {resetConfigMutation.isPending
                  ? <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  : <Undo2 className="mr-2 h-4 w-4" />
                }
                重置默认
              </Button>
              <Button
                onClick={handleSubmitConfig}
                disabled={updateConfigMutation.isPending}
              >
                {updateConfigMutation.isPending
                  ? <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  : <Save className="mr-2 h-4 w-4" />
                }
                提交更改
              </Button>
            </>
          ) : null
        }
      />

      <Card>
        <CardHeader>
          <CardTitle className="text-base">选择配置模块</CardTitle>
        </CardHeader>
        <CardContent>
          <Select
            value={selectedModule ?? undefined}
            onValueChange={handleModuleChange}
            itemToStringLabel={(v: string) => moduleOptions.find(o => o.value === v)?.label ?? v}
          >
            <SelectTrigger className="w-full">
              <SelectValue placeholder="请选择一个配置模块" />
            </SelectTrigger>
            <SelectContent>
              {moduleOptions.map(option => (
                <SelectItem key={option.value} value={option.value}>
                  {option.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          {selectedModule && (
            <>
              <Separator className="my-4" />

              {(configLoading || schemaLoading) && (
                <div className="flex justify-center py-8">
                  <Spinner className="size-8" />
                </div>
              )}

              {configError && (
                <Alert variant="destructive" className="mb-4">
                  <AlertTitle>配置加载失败</AlertTitle>
                  <AlertDescription>无法加载选定模块的配置数据</AlertDescription>
                </Alert>
              )}

              {schemaError && (
                <Alert variant="destructive" className="mb-4">
                  <AlertTitle>模式加载失败</AlertTitle>
                  <AlertDescription>无法加载选定模块的配置模式</AlertDescription>
                </Alert>
              )}

              {isConfigLoaded && (
                <div>
                  <div className="mb-4">
                    <h4 className="text-lg font-semibold">配置表单</h4>
                    <p className="text-sm text-muted-foreground">
                      模块: {moduleSchema.module_name} |
                      版本: {moduleSchema.version} |
                      类型: {moduleSchema.schema_class}
                    </p>
                  </div>

                  <Form
                    schema={moduleSchema.json_schema as RJSFSchema}
                    formData={formData}
                    validator={validator}
                    onChange={handleFormChange}
                    onSubmit={handleSubmitConfig}
                    onError={(errors: any) => console.log('Form validation errors:', errors)}
                    liveValidate="onChange"
                  >
                    <div />
                  </Form>
                </div>
              )}
            </>
          )}
        </CardContent>
      </Card>

      {/* Submit confirm dialog */}
      <Dialog
        open={!!submitDialogData}
        onOpenChange={(open) => {
          if (!open && !updateConfigMutation.isPending) setSubmitDialogData(null)
        }}
      >
        <DialogContent className="sm:max-w-200">
          <DialogHeader>
            <DialogTitle>提交配置更改</DialogTitle>
            <DialogDescription>确定要提交配置更改吗？</DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            {submitDialogData?.hasChanges && (
              <div>
                <p className="mb-2 text-sm font-semibold">配置差异预览：</p>
                <div className="rounded-md border overflow-hidden h-100">
                  <MonacoDiffEditor
                    height="400px"
                    language="json"
                    original={JSON.stringify(submitDialogData.latestConfigData, null, 2)}
                    modified={JSON.stringify(formData, null, 2)}
                    options={{
                      minimap: { enabled: false },
                      scrollBeyondLastLine: false,
                      fontSize: 12,
                      lineNumbers: 'off',
                      folding: false,
                      wordWrap: 'on',
                      scrollbar: { vertical: 'visible', horizontal: 'visible' },
                    }}
                  />
                </div>
              </div>
            )}
            {submitDialogData && !submitDialogData.hasChanges && (
              <Alert>
                <Info className="h-4 w-4" />
                <AlertTitle>没有检测到配置更改</AlertTitle>
                <AlertDescription>
                  当前表单配置与服务器配置相同，提交后不会有任何变化。
                </AlertDescription>
              </Alert>
            )}
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setSubmitDialogData(null)}
              disabled={updateConfigMutation.isPending}
            >
              取消
            </Button>
            <Button
              onClick={handleConfirmSubmit}
              disabled={updateConfigMutation.isPending}
              variant={submitDialogData?.hasChanges ? 'default' : 'outline'}
            >
              {updateConfigMutation.isPending && <Loader2 className="mr-1 h-4 w-4 animate-spin" />}
              确认提交
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Compare dialog */}
      <Dialog open={isCompareVisible} onOpenChange={setIsCompareVisible}>
        <DialogContent className="sm:max-w-350">
          <DialogHeader>
            <DialogTitle>配置差异对比</DialogTitle>
            <DialogDescription>
              左侧为服务器当前配置，右侧为表单编辑的配置。高亮显示的是差异部分。
            </DialogDescription>
          </DialogHeader>
          <div className="rounded-md border overflow-hidden h-150">
            <MonacoDiffEditor
              height="600px"
              language="json"
              original={JSON.stringify(moduleConfig?.config_data || {}, null, 2)}
              modified={JSON.stringify(formData, null, 2)}
              originalTitle="服务器当前配置"
              modifiedTitle="表单编辑配置"
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setIsCompareVisible(false)}>
              关闭
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {confirmDialog}
    </div>
  )
}

export default DynamicConfig
