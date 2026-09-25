import React, { useRef, useState } from 'react'
import { toast } from 'sonner'
import {
  RefreshCw,
  Server,
  GitCompare,
  ArrowLeftRight,
  HelpCircle,
  Settings,
} from 'lucide-react'
import type { UseQueryResult } from '@tanstack/react-query'

import { Button } from '@/shared/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/shared/ui/card'
import { Alert, AlertTitle, AlertDescription } from '@/shared/ui/alert'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/shared/ui/dialog'

import { ComposeYamlEditor, MonacoDiffEditor } from '@/shared/editors/index'
import { ComposeDiffDialog } from '@/shared/editors/compose/index'
import RebuildProgressDialog from '@/features/configuration/components/RebuildProgressDialog'
import ConvertModeDialog from '@/features/configuration/components/ConvertModeDialog'
import DockerComposeHelpDialog from '@/shared/editors/DockerComposeHelpDialog'
import PageHeader from '@/shared/layout/PageHeader'
import { useConfirm } from '@/shared/hooks/useConfirm'
import { useConfigurationSession } from '@/features/configuration/useConfigurationSession'
import { ConfigurationConflict } from '@/features/configuration/components/ConfigurationConflict'
import { useConfigurationCommands } from '@/features/configuration/commands'
import { isConfigurationConflict } from '@/features/configuration/api'
import type { ComposeConfiguration } from '@/features/configuration/contracts'

interface ServerInfo {
  name: string
}

interface DirectModeProps {
  serverId: string
  serverInfo: ServerInfo
  onConverted: () => void
  composeContent: string
  composeVersion: string
  composeQuery: UseQueryResult<ComposeConfiguration, Error>
  rebuildTaskId: string | null
  setRebuildTaskId: (id: string | null) => void
  isRebuildDialogOpen: boolean
  setIsRebuildDialogOpen: (visible: boolean) => void
  isConvertDialogOpen: boolean
  setIsConvertDialogOpen: (visible: boolean) => void
}

const DirectMode: React.FC<DirectModeProps> = ({
  serverId,
  serverInfo,
  onConverted,
  composeContent,
  composeVersion,
  composeQuery,
  rebuildTaskId,
  setRebuildTaskId,
  isRebuildDialogOpen,
  setIsRebuildDialogOpen,
  isConvertDialogOpen,
  setIsConvertDialogOpen,
}) => {
  const { confirm, confirmDialog } = useConfirm()
  const { updateCompose: updateComposeMutation } = useConfigurationCommands(serverId)
  const session = useConfigurationSession({ version: composeVersion, value: composeContent, description: composeContent, readAt: composeQuery.dataUpdatedAt }, true)
  const submittedDraft = useRef<string | null>(null)
  const { draft: rawYaml, setDraft: setRawYaml } = session
  const refresh = async () => {
    const result = await composeQuery.refetch({ throwOnError: true })
    if (!result.data?.version) throw new Error('配置版本缺失')
    return { version: result.data.version, value: result.data.yaml_content, description: result.data.yaml_content, readAt: result.dataUpdatedAt }
  }
  const handleFailure = (code?: string) => {
    if (code === 'configuration_conflict') { session.markConflict(); void refresh().catch(() => undefined) }
  }
  const [isCompareVisible, setIsCompareVisible] = useState(false)
  const [isHelpDialogOpen, setIsHelpDialogOpen] = useState(false)
  const [isSubmitConfirmVisible, setIsSubmitConfirmVisible] = useState(false)
  const [editorKey, setEditorKey] = useState(0)
  const handleSubmitAndRebuild = async () => {
    try {
      const latest = await refresh()
      if (latest.version !== session.baseline.version || !session.canSubmit) { session.markConflict(); return }
      setIsSubmitConfirmVisible(true)
    } catch {
      toast.error('获取最新配置失败，已保留编辑内容，请重试')
    }
  }

  const handleConfirmRebuild = async () => {
    try {
      submittedDraft.current = rawYaml
      const result = await updateComposeMutation.mutateAsync({ value: rawYaml, version: session.baseline.version })
      setIsSubmitConfirmVisible(false)
      setRebuildTaskId(result.task_id)
      setIsRebuildDialogOpen(true)
    } catch (error: any) {
      if (isConfigurationConflict(error)) { setIsSubmitConfirmVisible(false); handleFailure('configuration_conflict') }
      toast.error(`配置提交失败: ${error.message}`)
    }
  }

  const handleReset = () => {
    confirm({
      title: '重新载入配置',
      description: '确定要重新载入配置吗？这将丢失当前编辑器中的更改，恢复到服务器的在线配置。',
      confirmText: '确认',
      cancelText: '取消',
      onConfirm: async () => {
        try {
          session.reset(await refresh())
          setEditorKey(prev => prev + 1)
          toast.info('配置已重新载入到服务器在线状态')
        } catch {
          toast.error('重新载入失败，已保留编辑内容')
        }
      },
    })
  }

  const handleCompare = async () => {
    try {
      await composeQuery.refetch({ throwOnError: true })
      setIsCompareVisible(true)
    } catch {
      toast.error('获取最新配置失败，使用当前缓存的配置进行对比')
      setIsCompareVisible(true)
    }
  }

  const handleYamlChange = (value: string | undefined) => {
    if (value !== undefined) {
      setRawYaml(value)
    }
  }

  return (
    <div className="flex flex-col h-full gap-4">
      <PageHeader
        title="设置"
        icon={<Settings className="h-5 w-5" />}
        serverTag={serverInfo.name}
        actions={
          <>
            <Button
              variant="outline"
              onClick={() => setIsConvertDialogOpen(true)}
            >
              <ArrowLeftRight className="mr-1 h-4 w-4" />
              转换为模板模式
            </Button>
            <Button
              variant="outline"
              onClick={handleCompare}
            >
              <GitCompare className="mr-1 h-4 w-4" />
              差异对比
            </Button>
            <Button
              variant="outline"
              onClick={handleReset}
            >
              <RefreshCw className="mr-1 h-4 w-4" />
              重新载入
            </Button>
            <Button
              variant="destructive"
              onClick={handleSubmitAndRebuild}
              disabled={!session.canSubmit}
            >
              <Server className="mr-1 h-4 w-4" />
              提交并重建
            </Button>
          </>
        }
      />

      <ConfigurationConflict {...session} needed={session.needsComparison} draftDescription={rawYaml} refresh={refresh} />

      <Card className="flex-1 min-h-0 flex flex-col">
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle>Docker Compose 配置</CardTitle>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setIsHelpDialogOpen(true)}
            >
              <HelpCircle className="mr-1 h-4 w-4" />
              配置帮助
            </Button>
          </div>
          <p className="text-xs text-muted-foreground">此处的修改在点击提交并重建后才会生效，退出该页面将丢失未保存的更改。</p>
        </CardHeader>
        <CardContent className="flex flex-col flex-1 min-h-0 p-0!">
          <ComposeYamlEditor
            key={editorKey}
            className="h-full"
            height="100%"
            value={rawYaml}
            onChange={handleYamlChange}
            path="docker-compose.yml"
          />
        </CardContent>
      </Card>

      <ComposeDiffDialog
        open={isCompareVisible}
        onClose={() => setIsCompareVisible(false)}
        originalContent={composeContent || ''}
        modifiedContent={rawYaml}
        originalTitle="服务器当前配置"
        modifiedTitle="本地编辑配置"
      />

      <DockerComposeHelpDialog
        open={isHelpDialogOpen}
        onCancel={() => setIsHelpDialogOpen(false)}
        page="ServerCompose"
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
          if (typeof result?.version === 'string' && submittedDraft.current !== null) session.markApplied({ version: result.version, value: submittedDraft.current, description: submittedDraft.current })
          submittedDraft.current = null
          setIsRebuildDialogOpen(false)
          setRebuildTaskId(null)
          setEditorKey(prev => prev + 1)
        }}
      />

      <ConvertModeDialog
        open={isConvertDialogOpen}
        serverId={serverId}
        currentMode="direct"
        onClose={() => setIsConvertDialogOpen(false)}
        initialVersion={composeVersion}
        onSuccess={onConverted}
      />

      <Dialog open={isSubmitConfirmVisible} onOpenChange={(o) => !o && setIsSubmitConfirmVisible(false)}>
        <DialogContent className="sm:max-w-200">
          <DialogHeader>
            <DialogTitle>提交并重建服务器</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <p className="text-sm">确定要提交配置并重建服务器吗？这将下线当前服务器并使用新配置重新创建。</p>
            {rawYaml.trim() !== composeContent?.trim() ? (
              <div>
                <div className="mb-2">
                  <strong className="text-sm">配置差异预览：</strong>
                </div>
                <div className="border rounded-md overflow-hidden h-150">
                  <MonacoDiffEditor
                    height="600px"
                    language="yaml"
                    original={composeContent || ''}
                    modified={rawYaml}
                    options={{
                      minimap: { enabled: false },
                      scrollBeyondLastLine: false,
                      fontSize: 12,
                      lineNumbers: 'off',
                      folding: false,
                      wordWrap: 'on',
                      scrollbar: {
                        vertical: 'visible',
                        horizontal: 'visible'
                      }
                    }}
                  />
                </div>
              </div>
            ) : (
              <Alert>
                <AlertTitle>没有检测到配置更改</AlertTitle>
                <AlertDescription>当前编辑的配置与服务器配置相同，重建后不会有任何变化。</AlertDescription>
              </Alert>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setIsSubmitConfirmVisible(false)}>取消</Button>
            <Button
              variant="destructive"
              onClick={handleConfirmRebuild}
              disabled={updateComposeMutation.isPending || !session.canSubmit}
            >
              确认重建
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {confirmDialog}
    </div>
  )
}

export default DirectMode
