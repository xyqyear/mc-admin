import React from 'react'
import { Modal, Button, Alert } from 'antd'
import { DiffOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { SimpleEditor } from '@/components/editors'
import type { FileItem } from '@/types/Server'

interface FileEditModalProps {
  open: boolean
  onCancel: () => void
  onSave: () => void
  onShowDiff: () => void
  editingFile: FileItem | null
  fileContent: string
  setFileContent: (content: string) => void
  originalFileContent: string
  isLoadingContent: boolean
  confirmLoading: boolean
  serverId: string
  getCurrentFileLanguageConfig: () => {
    language: string
    options: any
    config: any
    composeWarning?: {
      title: string
      message: string
      linkText: string
      severity: 'info' | 'warning' | 'error'
    }
  }
}

const FileEditModal: React.FC<FileEditModalProps> = ({
  open,
  onCancel,
  onSave,
  onShowDiff,
  editingFile,
  fileContent,
  setFileContent,
  originalFileContent,
  isLoadingContent,
  confirmLoading,
  serverId,
  getCurrentFileLanguageConfig
}) => {
  const navigate = useNavigate()

  const handleCancel = () => {
    onCancel()
  }

  const footer = [
    <Button
      key="diff"
      icon={<DiffOutlined />}
      onClick={onShowDiff}
      disabled={!originalFileContent || fileContent === originalFileContent}
    >
      差异对比
    </Button>,
    <Button key="cancel" onClick={handleCancel}>
      取消
    </Button>,
    <Button
      key="save"
      type="primary"
      onClick={onSave}
      loading={confirmLoading}
    >
      保存
    </Button>,
  ]

  return (
    <Modal
      title={`编辑文件: ${editingFile?.name}`}
      open={open}
      onOk={onSave}
      onCancel={handleCancel}
      width={800}
      okText="保存"
      cancelText="取消"
      confirmLoading={confirmLoading}
      footer={footer}
    >
      <div className="space-y-4">
        <Alert
          message="文件编辑"
          description="修改文件内容后点击保存。请谨慎编辑配置文件，错误的配置可能导致服务器无法启动。"
          type="warning"
          showIcon
        />
        {isLoadingContent ? (
          <div className="text-center py-8">加载文件内容中...</div>
        ) : (
          (() => {
            const { language, options, config, composeWarning } = getCurrentFileLanguageConfig()
            return (
              <div className="space-y-3">
                {/* Compose override warning */}
                {composeWarning && (
                  <Alert
                    message={composeWarning.title}
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
                )}

                {/* Language support indicator */}
                {config?.supportsValidation && (
                  <div className="text-xs text-gray-500 px-2">
                    <span className="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-blue-100 text-blue-800">
                      {config?.description} - 支持语法检查
                    </span>
                  </div>
                )}

                <SimpleEditor
                  height="500px"
                  language={language}
                  value={fileContent}
                  onChange={(value: string | undefined) => value !== undefined && setFileContent(value)}
                  theme="vs-light"
                  options={options}
                />
              </div>
            )
          })()
        )}
      </div>
    </Modal>
  )
}

export default FileEditModal