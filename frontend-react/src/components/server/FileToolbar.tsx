import React from 'react'
import {
  Trash2,
  Plus,
  ArrowUp,
  Upload,
  Archive,
  Wrench,
} from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Spinner } from '@/components/ui/spinner'
import { RefreshButton } from '@/components/common/RefreshButton'
import FileSnapshotActions from '@/components/files/FileSnapshotActions'

interface FileToolbarProps {
  currentPath: string
  selectedFiles: string[]
  serverId: string
  isLoadingFiles: boolean
  createArchiveMutation: { isPending: boolean }
  populateServerMutation: { isPending: boolean }
  bulkDeleteMutation: { isPending: boolean }
  restoreOwnershipMutation: { isPending: boolean }
  onNavigateToParent: () => void
  onRefresh: () => void
  onUpload: () => void
  onCreateFile: () => void
  onBulkDelete: () => void
  onCompressServer: () => void
  onReplaceServerFiles: () => void
  onRestoreOwnership: () => void
  onRefreshSnapshot?: () => void
}

const FileToolbar: React.FC<FileToolbarProps> = ({
  currentPath,
  selectedFiles,
  serverId,
  isLoadingFiles,
  createArchiveMutation,
  populateServerMutation,
  bulkDeleteMutation,
  restoreOwnershipMutation,
  onNavigateToParent,
  onRefresh,
  onUpload,
  onCreateFile,
  onBulkDelete,
  onCompressServer,
  onReplaceServerFiles,
  onRestoreOwnership,
  onRefreshSnapshot
}) => {
  return (
    <>
      {currentPath !== '/' && (
        <Button variant="outline" onClick={onNavigateToParent}>
          <ArrowUp className="mr-2 h-4 w-4" />
          返回上级
        </Button>
      )}

      {currentPath === '/' && (
        <>
          <FileSnapshotActions
            serverId={serverId}
            path="/"
            isServerMode={true}
            onRefresh={onRefreshSnapshot}
          />
          <Button
            variant="outline"
            onClick={onCompressServer}
            disabled={createArchiveMutation.isPending}
          >
            {createArchiveMutation.isPending
              ? <Spinner className="mr-2 size-4" />
              : <Archive className="mr-2 h-4 w-4" />
            }
            打包服务器
          </Button>
          <Button
            variant="destructive"
            onClick={onReplaceServerFiles}
            disabled={populateServerMutation.isPending}
          >
            {populateServerMutation.isPending
              ? <Spinner className="mr-2 size-4" />
              : <Archive className="mr-2 h-4 w-4" />
            }
            替换服务器文件
          </Button>
        </>
      )}

      <Button
        variant="outline"
        onClick={onRestoreOwnership}
        disabled={restoreOwnershipMutation.isPending}
      >
        {restoreOwnershipMutation.isPending
          ? <Spinner className="mr-2 size-4" />
          : <Wrench className="mr-2 h-4 w-4" />
        }
        修复文件所有权
      </Button>
      <Button variant="outline" onClick={onUpload}>
        <Upload className="mr-2 h-4 w-4" />
        上传文件
      </Button>
      <Button variant="outline" onClick={onCreateFile}>
        <Plus className="mr-2 h-4 w-4" />
        新建文件/文件夹
      </Button>
      <RefreshButton onClick={onRefresh} isRefreshing={isLoadingFiles} />

      {selectedFiles.length > 0 && (
        <Button
          variant="destructive"
          onClick={onBulkDelete}
          disabled={bulkDeleteMutation.isPending}
        >
          {bulkDeleteMutation.isPending
            ? <Spinner className="mr-2 size-4" />
            : <Trash2 className="mr-2 h-4 w-4" />
          }
          批量删除 ({selectedFiles.length})
        </Button>
      )}
    </>
  )
}

export default FileToolbar
