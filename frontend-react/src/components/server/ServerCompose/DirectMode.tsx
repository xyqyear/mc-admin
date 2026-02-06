import React, { useState, useRef, useEffect } from 'react'
import { Card, Button, Alert, App } from 'antd'
import {
  ReloadOutlined,
  ExclamationCircleOutlined,
  CloudServerOutlined,
  DiffOutlined,
  SwapOutlined,
  QuestionCircleOutlined,
  SettingOutlined,
} from '@ant-design/icons'
import type { UseQueryResult } from '@tanstack/react-query'
import { ComposeYamlEditor, MonacoDiffEditor } from '@/components/editors'
import { ComposeDiffModal } from '@/components/modals/ServerCompose'
import RebuildProgressModal from '@/components/modals/RebuildProgressModal'
import ConvertModeModal from '@/components/modals/ConvertModeModal'
import DockerComposeHelpModal from '@/components/modals/DockerComposeHelpModal'
import PageHeader from '@/components/layout/PageHeader'
import { useServerMutations } from '@/hooks/mutations/useServerMutations'

interface ServerInfo {
  name: string
}

interface DirectModeProps {
  serverId: string
  serverInfo: ServerInfo
  composeContent: string
  composeQuery: UseQueryResult<string, Error>
  rebuildTaskId: string | null
  setRebuildTaskId: (id: string | null) => void
  isRebuildModalVisible: boolean
  setIsRebuildModalVisible: (visible: boolean) => void
  isConvertModalVisible: boolean
  setIsConvertModalVisible: (visible: boolean) => void
  onConvertModeSuccess: () => void
}

const DirectMode: React.FC<DirectModeProps> = ({
  serverId,
  serverInfo,
  composeContent,
  composeQuery,
  rebuildTaskId,
  setRebuildTaskId,
  isRebuildModalVisible,
  setIsRebuildModalVisible,
  isConvertModalVisible,
  setIsConvertModalVisible,
  onConvertModeSuccess,
}) => {
  const { modal, message } = App.useApp()
  const { useUpdateCompose } = useServerMutations()
  const updateComposeMutation = useUpdateCompose(serverId)

  const [rawYaml, setRawYaml] = useState('')
  const [isCompareVisible, setIsCompareVisible] = useState(false)
  const [isHelpModalVisible, setIsHelpModalVisible] = useState(false)
  const [editorKey, setEditorKey] = useState(0)
  const editorRef = useRef<any>(null)

  useEffect(() => {
    if (composeContent) {
      setRawYaml(composeContent)
    }
  }, [composeContent, serverId])

  const handleSubmitAndRebuild = async () => {
    try {
      await composeQuery.refetch()
    } catch {
      message.warning('获取最新配置失败，将使用当前缓存的配置进行对比')
    }

    const hasChanges = rawYaml.trim() !== composeContent?.trim()

    modal.confirm({
      title: '提交并重建服务器',
      content: (
        <div className="space-y-4">
          <p>确定要提交配置并重建服务器吗？这将下线当前服务器并使用新配置重新创建。</p>
          {hasChanges && (
            <div>
              <div className="mb-2">
                <strong>配置差异预览：</strong>
              </div>
              <div style={{
                border: '1px solid #d9d9d9',
                borderRadius: '6px',
                overflow: 'hidden',
                height: '600px',
                backgroundColor: '#fafafa'
              }}>
                <MonacoDiffEditor
                  height="600px"
                  language="yaml"
                  original={composeContent || ''}
                  modified={rawYaml}
                  theme="vs-light"
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
          )}
          {!hasChanges && (
            <Alert
              title="没有检测到配置更改"
              description="当前编辑的配置与服务器配置相同，重建后不会有任何变化。"
              type="info"
              showIcon
              className="mt-2"
            />
          )}
        </div>
      ),
      width: 800,
      okText: '确认重建',
      okType: 'danger',
      cancelText: '取消',
      icon: <ExclamationCircleOutlined />,
      onOk: async () => {
        try {
          const result = await updateComposeMutation.mutateAsync(rawYaml)
          setRebuildTaskId(result.task_id)
          setIsRebuildModalVisible(true)
        } catch (error: any) {
          message.error(`配置提交失败: ${error.message}`)
        }
      }
    })
  }

  const handleReset = () => {
    modal.confirm({
      title: '重新载入配置',
      content: '确定要重新载入配置吗？这将丢失当前编辑器中的更改，恢复到服务器的在线配置。',
      okText: '确认',
      cancelText: '取消',
      icon: <ExclamationCircleOutlined />,
      onOk: () => {
        const originalConfig = composeContent || ''
        setRawYaml(originalConfig)
        setEditorKey(prev => prev + 1)
        setTimeout(() => {
          if (editorRef.current) {
            editorRef.current.setValue(originalConfig)
          }
        }, 100)
        message.info('配置已重新载入到服务器在线状态')
      }
    })
  }

  const handleCompare = async () => {
    try {
      await composeQuery.refetch()
      setIsCompareVisible(true)
    } catch {
      message.error('获取最新配置失败，使用当前缓存的配置进行对比')
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
        icon={<SettingOutlined />}
        serverTag={serverInfo.name}
        actions={
          <>
            <Button
              icon={<SwapOutlined />}
              onClick={() => setIsConvertModalVisible(true)}
            >
              转换为模板模式
            </Button>
            <Button
              icon={<DiffOutlined />}
              onClick={handleCompare}
            >
              差异对比
            </Button>
            <Button
              icon={<ReloadOutlined />}
              onClick={handleReset}
            >
              重新载入
            </Button>
            <Button
              type="primary"
              danger
              icon={<CloudServerOutlined />}
              onClick={handleSubmitAndRebuild}
            >
              提交并重建
            </Button>
          </>
        }
      />

      <Card
        className="flex-1 min-h-0 flex flex-col"
        classNames={{ body: "flex flex-col flex-1 min-h-0 !p-0" }}
        title={
          <div className="flex items-center justify-between w-full">
            <div className="flex items-center gap-3">
              <span>Docker Compose 配置</span>
              <span className="text-xs text-gray-400 font-normal">此处的修改在点击提交并重建后才会生效，退出该页面将丢失未保存的更改。</span>
            </div>
            <Button
              size="small"
              icon={<QuestionCircleOutlined />}
              onClick={() => setIsHelpModalVisible(true)}
              type="text"
            >
              配置帮助
            </Button>
          </div>
        }
      >
        <ComposeYamlEditor
          key={editorKey}
          className="h-full"
          height="100%"
          value={rawYaml}
          onChange={handleYamlChange}
          onMount={(editor: any) => {
            editorRef.current = editor
          }}
          theme="vs-light"
          path="docker-compose.yml"
        />
      </Card>

      <ComposeDiffModal
        open={isCompareVisible}
        onClose={() => setIsCompareVisible(false)}
        originalContent={composeContent || ''}
        modifiedContent={rawYaml}
        originalTitle="服务器当前配置"
        modifiedTitle="本地编辑配置"
      />

      <DockerComposeHelpModal
        open={isHelpModalVisible}
        onCancel={() => setIsHelpModalVisible(false)}
        page="ServerCompose"
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
          composeQuery.refetch()
          setEditorKey(prev => prev + 1)
        }}
      />

      <ConvertModeModal
        open={isConvertModalVisible}
        serverId={serverId}
        currentMode="direct"
        onClose={() => setIsConvertModalVisible(false)}
        onSuccess={onConvertModeSuccess}
      />
    </div>
  )
}

export default DirectMode
