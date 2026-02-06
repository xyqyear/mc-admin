import React from 'react'
import { Modal, Button, Alert } from 'antd'
import { MonacoDiffEditor } from '@/components/editors'

export interface ComposeDiffModalProps {
  open: boolean
  onClose: () => void
  originalContent: string
  modifiedContent: string
  originalTitle?: string
  modifiedTitle?: string
  title?: string
  description?: string
  loading?: boolean
}

const ComposeDiffModal: React.FC<ComposeDiffModalProps> = ({
  open,
  onClose,
  originalContent,
  modifiedContent,
  originalTitle = '服务器当前配置',
  modifiedTitle = '本地编辑配置',
  title = '配置差异对比',
  description = '左侧为服务器当前配置，右侧为本地编辑的配置。高亮显示的是差异部分。',
}) => {
  return (
    <Modal
      title={title}
      open={open}
      onCancel={onClose}
      width={1400}
      footer={[
        <Button key="close" onClick={onClose}>
          关闭
        </Button>
      ]}
    >
      <div className="space-y-4">
        <Alert
          title="差异对比视图"
          description={description}
          type="info"
          showIcon
        />
        <div style={{ border: '1px solid #d9d9d9', borderRadius: '6px', overflow: 'hidden', height: '600px' }}>
          <MonacoDiffEditor
            key={`diff-${originalContent?.length || 0}-${modifiedContent?.length || 0}`}
            height="600px"
            language="yaml"
            original={originalContent}
            modified={modifiedContent}
            originalTitle={originalTitle}
            modifiedTitle={modifiedTitle}
            theme="vs-light"
          />
        </div>
      </div>
    </Modal>
  )
}

export default ComposeDiffModal
