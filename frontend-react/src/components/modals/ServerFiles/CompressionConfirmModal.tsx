import React from 'react'
import { Modal, Alert } from 'antd'
import { FileZipOutlined, FolderOutlined, DatabaseOutlined } from '@ant-design/icons'
import type { FileItem } from '@/types/Server'

interface CompressionConfirmModalProps {
  open: boolean
  onCancel: () => void
  onOk: () => void
  confirmLoading: boolean
  selectedFile?: FileItem | null
  currentPath: string
  compressionType: 'file' | 'folder' | 'server'
  serverName?: string
}

const CompressionConfirmModal: React.FC<CompressionConfirmModalProps> = ({
  open,
  onCancel,
  onOk,
  confirmLoading,
  selectedFile,
  currentPath,
  compressionType,
  serverName = ''
}) => {
  const getCompressionDescription = () => {
    switch (compressionType) {
      case 'file':
        return `将压缩文件 "${selectedFile?.name}" 为压缩包`
      case 'folder':
        return selectedFile
          ? `将压缩文件夹 "${selectedFile.name}" 为压缩包`
          : `将压缩当前目录 "${currentPath}" 下的所有内容为压缩包`
      case 'server':
        return `将压缩整个服务器 "${serverName}" 的所有文件为压缩包`
      default:
        return ''
    }
  }

  const getCompressionIcon = () => {
    switch (compressionType) {
      case 'file':
        return <FileZipOutlined className="text-blue-500" />
      case 'folder':
        return <FolderOutlined className="text-orange-500" />
      case 'server':
        return <DatabaseOutlined className="text-green-500" />
      default:
        return <FileZipOutlined className="text-blue-500" />
    }
  }

  const getCompressionTitle = () => {
    switch (compressionType) {
      case 'file':
        return '压缩单个文件'
      case 'folder':
        return '压缩文件夹'
      case 'server':
        return '压缩整个服务器'
      default:
        return '创建压缩包'
    }
  }

  return (
    <Modal
      title="创建压缩包"
      open={open}
      onOk={onOk}
      onCancel={confirmLoading ? undefined : onCancel}
      confirmLoading={confirmLoading}
      okText={confirmLoading ? "压缩中..." : "开始压缩"}
      cancelText="取消"
      cancelButtonProps={{ disabled: confirmLoading }}
      closable={!confirmLoading}
      maskClosable={!confirmLoading}
      width={500}
    >
      <div className="space-y-4">
        <Alert
          message="压缩包创建"
          description="确认要创建压缩包吗？压缩完成后会自动保存到压缩包管理中。"
          type="info"
          showIcon
        />

        <div className="bg-gray-50 p-4 rounded border">
          <div className="flex items-center space-x-3 mb-2">
            {getCompressionIcon()}
            <span className="font-medium text-lg">{getCompressionTitle()}</span>
          </div>
          <div className="text-gray-600 ml-8">
            {getCompressionDescription()}
          </div>
        </div>

        <Alert
          message="注意事项"
          description="压缩过程可能需要一些时间，特别是在压缩整个服务器时。压缩完成后压缩包将出现在压缩包管理界面。"
          type="warning"
          showIcon
        />

        {confirmLoading && (
          <Alert
            message="正在压缩中..."
            description="压缩正在进行中，请不要关闭此窗口，否则无法收到压缩完成的提示。压缩可能需要几分钟时间，请耐心等待。"
            type="info"
            showIcon
          />
        )}
      </div>
    </Modal>
  )
}

export default CompressionConfirmModal