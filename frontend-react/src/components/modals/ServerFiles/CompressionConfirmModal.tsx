import React from 'react'
import { Modal, Alert, Progress, App } from 'antd'
import { FileZipOutlined, FolderOutlined, DatabaseOutlined } from '@ant-design/icons'
import type { FileItem } from '@/types/Server'
import type { BackgroundTask } from '@/stores/useBackgroundTaskStore'

interface CompressionConfirmModalProps {
  open: boolean
  onCancel: () => void
  onOk: () => void
  confirmLoading: boolean
  task?: BackgroundTask | null
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
  task,
  selectedFile,
  currentPath,
  compressionType,
  serverName = ''
}) => {
  const { message } = App.useApp()
  const isTaskRunning = task && (task.status === 'running' || task.status === 'pending')

  const handleClose = () => {
    if (isTaskRunning) {
      message.info('压缩进度可在右下角任务管理中查看')
    }
    onCancel()
  }

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
      onCancel={handleClose}
      confirmLoading={confirmLoading}
      okText={confirmLoading || isTaskRunning ? "压缩中..." : "开始压缩"}
      okButtonProps={{ disabled: !!isTaskRunning }}
      cancelText="取消"
      cancelButtonProps={{ disabled: confirmLoading && !isTaskRunning }}
      closable={true}
      maskClosable={false}
      width={500}
    >
      <div className="space-y-4">
        <Alert
          title="压缩包创建"
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
          title="注意事项"
          description="压缩过程可能需要一些时间，特别是在压缩整个服务器时。压缩完成后压缩包将出现在压缩包管理界面。"
          type="warning"
          showIcon
        />

        {isTaskRunning && (
          <div className="space-y-2">
            <Progress
              percent={task.progress ?? 0}
              status="active"
              format={(percent) => `${percent}%`}
            />
            <div className="text-gray-500 text-sm">{task.message || '正在压缩...'}</div>
          </div>
        )}

        {(confirmLoading && !isTaskRunning) && (
          <Alert
            title="正在提交任务..."
            description="正在提交压缩任务，请稍候。"
            type="info"
            showIcon
          />
        )}
      </div>
    </Modal>
  )
}

export default CompressionConfirmModal