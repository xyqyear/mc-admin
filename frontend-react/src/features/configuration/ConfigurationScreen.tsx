import React, { useState } from 'react'
import { useParams, useNavigate } from 'react-router'

import { Button } from '@/shared/ui/button'
import { Alert, AlertTitle, AlertDescription } from '@/shared/ui/alert'

import LoadingSpinner from '@/shared/layout/LoadingSpinner'
import { useServerQueries } from '@/features/servers/queries'
import { useQuery } from '@tanstack/react-query'
import { useServerTemplatePreview, useServerTemplateConfig } from '@/features/configuration/queries'
import TemplateMode from '@/features/configuration/components/TemplateMode'
import DirectMode from '@/features/configuration/components/DirectMode'
import { composeOptions } from '@/features/configuration/queries'
import { useConfirm } from '@/shared/hooks/useConfirm'

const ConfigurationEditor: React.FC<{ id: string | undefined }> = ({ id }) => {
  const navigate = useNavigate()

  const { data: templatePreview, isLoading: previewLoading, error: previewError } = useServerTemplatePreview(id || null)
  const remoteMode = templatePreview?.is_template_based
  const [editorMode, setEditorMode] = useState<boolean | undefined>(undefined)
  const [requestedMode, setRequestedMode] = useState<boolean | null>(null)
  if (editorMode === undefined && remoteMode !== undefined) setEditorMode(remoteMode)
  if (requestedMode !== null && remoteMode === requestedMode && editorMode !== remoteMode) {
    setEditorMode(remoteMode)
    setRequestedMode(null)
  }
  const isTemplateBased = editorMode ?? remoteMode ?? false
  const { confirm, confirmDialog } = useConfirm()

  const { data: templateConfig, dataUpdatedAt: templateReadAt, isLoading: templateConfigLoading, error: templateConfigError, refetch: refetchTemplateConfig } = useServerTemplateConfig(
    isTemplateBased ? id || null : null
  )

  const { useServerInfo } = useServerQueries()
  const { data: serverInfo, isLoading: serverLoading, error: serverErrorMessage } = useServerInfo(id || '')
  const composeQuery = useQuery(composeOptions(id || ''))
  const composeContent = composeQuery.data?.yaml_content ?? ''

  const [rebuildTaskId, setRebuildTaskId] = useState<string | null>(null)
  const [isRebuildDialogOpen, setIsRebuildDialogOpen] = useState(false)
  const [isConvertDialogOpen, setIsConvertDialogOpen] = useState(false)

  if (!id) {
    return (
      <div className="flex justify-center items-center min-h-64">
        <Alert variant="destructive">
          <AlertTitle>参数错误</AlertTitle>
          <AlertDescription className="flex items-center justify-between">
            缺少服务器ID参数
            <Button variant="outline" size="sm" onClick={() => navigate('/overview')}>返回概览</Button>
          </AlertDescription>
        </Alert>
      </div>
    )
  }

  if (previewLoading || serverLoading || composeQuery.isLoading) {
    return <LoadingSpinner height="16rem" tip="加载配置文件中..." />
  }

  if (!serverInfo || (previewError && !templatePreview) || (composeQuery.isError && composeQuery.data === undefined) || (isTemplateBased && templateConfigError && !templateConfig)) {
    const errorMessage = previewError?.message || templateConfigError?.message || composeQuery.error?.message || serverErrorMessage?.message || `无法加载服务器 "${id}" 的配置信息`
    return (
      <div className="flex justify-center items-center min-h-64">
        <Alert variant="destructive">
          <AlertTitle>加载失败</AlertTitle>
          <AlertDescription className="flex items-center justify-between">
            {errorMessage}
            <Button variant="outline" size="sm" onClick={() => navigate('/overview')}>返回概览</Button>
          </AlertDescription>
        </Alert>
      </div>
    )
  }

  const modeChanged = remoteMode !== undefined && isTemplateBased !== remoteMode
  const modeNotice = modeChanged ? <Alert variant="destructive">
    <AlertTitle>在线编辑模式已变更</AlertTitle>
    <AlertDescription>当前草稿仍保留在原编辑器中。载入新模式前，请保存需要保留的内容。
      <Button onClick={() => confirm({ title: '载入新的编辑模式', description: '这将丢弃当前页面的本地草稿，并载入服务器在线配置。', onConfirm: () => { setEditorMode(remoteMode) } })}>载入新的编辑模式</Button>
    </AlertDescription>
  </Alert> : null

  if (isTemplateBased) {
    if (templateConfigLoading || !templateConfig) {
      return <LoadingSpinner height="16rem" tip="加载模板配置中..." />
    }

    return (
      <>{modeNotice}{confirmDialog}<TemplateMode
        key={id}
        serverId={id}
        serverInfo={serverInfo}
        templateConfig={templateConfig}
        templateReadAt={templateReadAt}
        composeContent={composeContent}
        composeVersion={composeQuery.data?.version ?? ''}
        composeQuery={composeQuery}
        refetchTemplateConfig={refetchTemplateConfig}
        rebuildTaskId={rebuildTaskId}
        setRebuildTaskId={setRebuildTaskId}
        isRebuildDialogOpen={isRebuildDialogOpen}
        setIsRebuildDialogOpen={setIsRebuildDialogOpen}
        isConvertDialogOpen={isConvertDialogOpen}
        setIsConvertDialogOpen={setIsConvertDialogOpen}
        onConverted={() => setRequestedMode(false)}
      /></>
    )
  }

  return (
    <>{modeNotice}{confirmDialog}<DirectMode
      key={id}
      serverId={id}
      serverInfo={serverInfo}
      composeContent={composeContent}
      composeVersion={composeQuery.data?.version ?? ''}
      composeQuery={composeQuery}
      rebuildTaskId={rebuildTaskId}
      setRebuildTaskId={setRebuildTaskId}
      isRebuildDialogOpen={isRebuildDialogOpen}
      setIsRebuildDialogOpen={setIsRebuildDialogOpen}
      isConvertDialogOpen={isConvertDialogOpen}
      setIsConvertDialogOpen={setIsConvertDialogOpen}
      onConverted={() => setRequestedMode(true)}
    /></>
  )
}

export default function ServerCompose() {
  const { id } = useParams<{ id: string }>()
  return <ConfigurationEditor key={id} id={id} />
}
