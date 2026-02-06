import React, { useState } from 'react'
import { Alert, Button } from 'antd'
import { useParams, useNavigate } from 'react-router-dom'
import LoadingSpinner from '@/components/layout/LoadingSpinner'
import { useServerDetailQueries } from '@/hooks/queries/page/useServerDetailQueries'
import { useServerTemplatePreview, useServerTemplateConfig } from '@/hooks/queries/base/useTemplateQueries'
import { TemplateMode, DirectMode } from '@/components/server/ServerCompose'

const ServerCompose: React.FC = () => {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()

  // Check if server is template-based
  const { data: templatePreview, isLoading: previewLoading } = useServerTemplatePreview(id || null)
  const isTemplateBased = templatePreview?.is_template_based ?? false

  // Template config for template-based servers
  const { data: templateConfig, isLoading: templateConfigLoading, refetch: refetchTemplateConfig } = useServerTemplateConfig(
    isTemplateBased ? id || null : null
  )

  // Server data
  const { useServerComposeData } = useServerDetailQueries(id || '')
  const {
    serverInfo,
    composeContent,
    serverLoading,
    serverError,
    serverErrorMessage,
    composeQuery
  } = useServerComposeData()

  // Shared state for rebuild modal
  const [rebuildTaskId, setRebuildTaskId] = useState<string | null>(null)
  const [isRebuildModalVisible, setIsRebuildModalVisible] = useState(false)
  const [isConvertModalVisible, setIsConvertModalVisible] = useState(false)

  // Missing server ID
  if (!id) {
    return (
      <div className="flex justify-center items-center min-h-64">
        <Alert
          message="参数错误"
          description="缺少服务器ID参数"
          type="error"
          action={
            <Button size="small" onClick={() => navigate('/overview')}>
              返回概览
            </Button>
          }
        />
      </div>
    )
  }

  // Loading state
  if (previewLoading || serverLoading || composeQuery.isLoading || !serverInfo) {
    return <LoadingSpinner height="16rem" tip="加载配置文件中..." />
  }

  // Error state
  if (serverError || composeQuery.isError) {
    const errorMessage = (serverErrorMessage as any)?.message || `无法加载服务器 "${id}" 的配置信息`
    return (
      <div className="flex justify-center items-center min-h-64">
        <Alert
          title="加载失败"
          description={errorMessage}
          type="error"
          action={
            <Button size="small" onClick={() => navigate('/overview')}>
              返回概览
            </Button>
          }
        />
      </div>
    )
  }

  const handleConvertModeSuccess = () => {
    composeQuery.refetch()
    refetchTemplateConfig()
  }

  // Template mode
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
        isRebuildModalVisible={isRebuildModalVisible}
        setIsRebuildModalVisible={setIsRebuildModalVisible}
        isConvertModalVisible={isConvertModalVisible}
        setIsConvertModalVisible={setIsConvertModalVisible}
        onConvertModeSuccess={handleConvertModeSuccess}
      />
    )
  }

  // Direct edit mode
  return (
    <DirectMode
      serverId={id}
      serverInfo={serverInfo}
      composeContent={composeContent || ''}
      composeQuery={composeQuery}
      rebuildTaskId={rebuildTaskId}
      setRebuildTaskId={setRebuildTaskId}
      isRebuildModalVisible={isRebuildModalVisible}
      setIsRebuildModalVisible={setIsRebuildModalVisible}
      isConvertModalVisible={isConvertModalVisible}
      setIsConvertModalVisible={setIsConvertModalVisible}
      onConvertModeSuccess={handleConvertModeSuccess}
    />
  )
}

export default ServerCompose
