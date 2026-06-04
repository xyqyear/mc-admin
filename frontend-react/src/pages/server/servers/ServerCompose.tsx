import React, { useState } from 'react'
import { useParams, useNavigate } from 'react-router'

import { Button } from '@/components/ui/button'
import { Alert, AlertTitle, AlertDescription } from '@/components/ui/alert'

import LoadingSpinner from '@/components/layout/LoadingSpinner'
import { useServerDetailQueries } from '@/hooks/queries/page/useServerDetailQueries'
import { useServerTemplatePreview, useServerTemplateConfig } from '@/hooks/queries/base/useTemplateQueries'
import { TemplateMode, DirectMode } from '@/components/server/ServerCompose'

const ServerCompose: React.FC = () => {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()

  const { data: templatePreview, isLoading: previewLoading } = useServerTemplatePreview(id || null)
  const isTemplateBased = templatePreview?.is_template_based ?? false

  const { data: templateConfig, isLoading: templateConfigLoading, refetch: refetchTemplateConfig } = useServerTemplateConfig(
    isTemplateBased ? id || null : null
  )

  const { useServerComposeData } = useServerDetailQueries(id || '')
  const {
    serverInfo,
    composeContent,
    serverLoading,
    serverError,
    serverErrorMessage,
    composeQuery
  } = useServerComposeData()

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

  if (previewLoading || serverLoading || composeQuery.isLoading || !serverInfo) {
    return <LoadingSpinner height="16rem" tip="加载配置文件中..." />
  }

  if (serverError || composeQuery.isError) {
    const errorMessage = (serverErrorMessage as any)?.message || `无法加载服务器 "${id}" 的配置信息`
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

  const handleConvertModeSuccess = () => {
    composeQuery.refetch()
    refetchTemplateConfig()
  }

  if (isTemplateBased) {
    if (templateConfigLoading || !templateConfig) {
      return <LoadingSpinner height="16rem" tip="加载模板配置中..." />
    }

    return (
      <TemplateMode
        serverId={id}
        serverInfo={serverInfo}
        templateConfig={templateConfig}
        composeContent={composeContent || ''}
        composeQuery={composeQuery}
        refetchTemplateConfig={refetchTemplateConfig}
        rebuildTaskId={rebuildTaskId}
        setRebuildTaskId={setRebuildTaskId}
        isRebuildDialogOpen={isRebuildDialogOpen}
        setIsRebuildDialogOpen={setIsRebuildDialogOpen}
        isConvertDialogOpen={isConvertDialogOpen}
        setIsConvertDialogOpen={setIsConvertDialogOpen}
        onConvertModeSuccess={handleConvertModeSuccess}
      />
    )
  }

  return (
    <DirectMode
      serverId={id}
      serverInfo={serverInfo}
      composeContent={composeContent || ''}
      composeQuery={composeQuery}
      rebuildTaskId={rebuildTaskId}
      setRebuildTaskId={setRebuildTaskId}
      isRebuildDialogOpen={isRebuildDialogOpen}
      setIsRebuildDialogOpen={setIsRebuildDialogOpen}
      isConvertDialogOpen={isConvertDialogOpen}
      setIsConvertDialogOpen={setIsConvertDialogOpen}
      onConvertModeSuccess={handleConvertModeSuccess}
    />
  )
}

export default ServerCompose
