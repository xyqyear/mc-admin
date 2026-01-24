import React from 'react'
import { Modal, Button, Alert } from 'antd'
import { useNavigate } from 'react-router-dom'
import { MonacoDiffEditor } from '@/components/editors'

interface FileDiffModalProps {
  open: boolean
  onCancel: () => void
  originalFileContent: string
  fileContent: string
  serverId: string
  getCurrentFileLanguageConfig: () => {
    language: string
    config?: {
      supportsValidation: boolean
      description: string
    }
    composeWarning?: {
      title: string
      message: string
      linkText: string
      severity: 'info' | 'warning' | 'error'
    }
  }
}

const FileDiffModal: React.FC<FileDiffModalProps> = ({
  open,
  onCancel,
  originalFileContent,
  fileContent,
  serverId,
  getCurrentFileLanguageConfig
}) => {
  const navigate = useNavigate()

  return (
    <Modal
      title="文件差异对比"
      open={open}
      onCancel={onCancel}
      width={1400}
      footer={[
        <Button key="close" onClick={onCancel}>
          关闭
        </Button>
      ]}
    >
      <div className="space-y-4">
        <Alert
          title="差异对比视图"
          description="左侧为文件原始内容，右侧为当前编辑的内容。高亮显示的是差异部分。"
          type="info"
          showIcon
        />
        {/* Compose override warning for diff view */}
        {(() => {
          const { composeWarning } = getCurrentFileLanguageConfig()
          return composeWarning && (
            <div className="mb-3">
              <Alert
                title={composeWarning.title}
                description={
                  <div className="space-y-2">
                    <p>{composeWarning.message}</p>
                    <Button
                      type="link"
                      size="small"
                      className="p-0 h-auto"
                      onClick={() => navigate(`/server/${serverId}/compose`)}
                    >
                      {composeWarning.linkText}
                    </Button>
                  </div>
                }
                type={composeWarning.severity}
                showIcon
                closable
              />
            </div>
          )
        })()}

        <div style={{ border: '1px solid #d9d9d9', borderRadius: '6px', overflow: 'hidden', height: '600px' }}>
          {(() => {
            const { language, config } = getCurrentFileLanguageConfig()
            return (
              <div className="h-full">
                {config?.supportsValidation && (
                  <div className="px-3 py-2 bg-gray-50 border-b text-xs text-gray-600">
                    <span className="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-blue-100 text-blue-800">
                      {config?.description} - 语法高亮已启用
                    </span>
                  </div>
                )}
                <MonacoDiffEditor
                  height={config?.supportsValidation ? "570px" : "600px"}
                  language={language}
                  original={originalFileContent}
                  modified={fileContent}
                  originalTitle="文件原始内容"
                  modifiedTitle="当前编辑内容"
                  theme="vs-light"
                />
              </div>
            )
          })()}
        </div>
      </div>
    </Modal>
  )
}

export default FileDiffModal