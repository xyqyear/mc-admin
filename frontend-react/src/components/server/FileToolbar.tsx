import React from 'react'
import { Button, Space } from 'antd'
import {
  DeleteOutlined,
  PlusOutlined,
  ArrowUpOutlined,
  ReloadOutlined,
  UploadOutlined,
  FileZipOutlined
} from '@ant-design/icons'
import FileSnapshotActions from '@/components/files/FileSnapshotActions'

interface FileToolbarProps {
  currentPath: string
  selectedFiles: string[]
  serverId: string
  isLoadingFiles: boolean
  createArchiveMutation: { isPending: boolean }
  populateServerMutation: { isPending: boolean }
  deleteFileMutation: { isPending: boolean }
  onNavigateToParent: () => void
  onRefresh: () => void
  onUpload: () => void
  onCreateFile: () => void
  onBulkDelete: () => void
  onCompressServer: () => void
  onReplaceServerFiles: () => void
  onRefreshSnapshot?: () => void
}

const FileToolbar: React.FC<FileToolbarProps> = ({
  currentPath,
  selectedFiles,
  serverId,
  isLoadingFiles,
  createArchiveMutation,
  populateServerMutation,
  deleteFileMutation,
  onNavigateToParent,
  onRefresh,
  onUpload,
  onCreateFile,
  onBulkDelete,
  onCompressServer,
  onReplaceServerFiles,
  onRefreshSnapshot
}) => {
  return (
    <Space wrap>
      {/* 返回上级按钮 */}
      {currentPath !== '/' && (
        <Button
          icon={<ArrowUpOutlined />}
          onClick={onNavigateToParent}
        >
          返回上级
        </Button>
      )}
      
      {/* 根目录特有的按钮 */}
      {currentPath === '/' && (
        <>
          <FileSnapshotActions 
            serverId={serverId} 
            path="/" 
            isServerMode={true} 
            onRefresh={onRefreshSnapshot} 
          />
          <Button
            icon={<FileZipOutlined />}
            onClick={onCompressServer}
            loading={createArchiveMutation.isPending}
          >
            打包服务器
          </Button>
          <Button
            icon={<FileZipOutlined />}
            danger
            onClick={onReplaceServerFiles}
            loading={populateServerMutation.isPending}
          >
            替换服务器文件
          </Button>
        </>
      )}
      
      {/* 通用按钮 */}
      <Button
        icon={<UploadOutlined />}
        onClick={onUpload}
      >
        上传文件
      </Button>
      <Button
        icon={<PlusOutlined />}
        onClick={onCreateFile}
      >
        新建文件/文件夹
      </Button>
      <Button
        icon={<ReloadOutlined />}
        onClick={onRefresh}
        loading={isLoadingFiles}
      >
        刷新
      </Button>
      
      {/* 批量删除按钮 */}
      {selectedFiles.length > 0 && (
        <Button
          icon={<DeleteOutlined />}
          danger
          onClick={onBulkDelete}
          loading={deleteFileMutation.isPending}
        >
          批量删除 ({selectedFiles.length})
        </Button>
      )}
    </Space>
  )
}

export default FileToolbar