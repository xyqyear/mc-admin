import React from 'react'
import {
  Plus,
  ArrowUp,
  Upload,
  Archive,
  Wrench,
} from 'lucide-react'

import { Button } from '@/shared/ui/button'
import { Spinner } from '@/shared/ui/spinner'
import { RefreshButton } from '@/shared/components/RefreshButton'
import { ButtonLink } from '@/shared/components/ButtonLink'
import FileSnapshotActions from '@/features/files/components/FileSnapshotActions'

interface FileToolbarProps {
  currentPath: string
  parentHref: string
  serverId: string
  isLoadingFiles: boolean
  createArchiveMutation: { isPending: boolean }
  populateServerMutation: { isPending: boolean }
  restoreOwnershipMutation: { isPending: boolean }
  onNavigateToParent: () => void
  onRefresh: () => void
  onUpload: () => void
  onCreateFile: () => void
  onCompressServer: () => void
  onReplaceServerFiles: () => void
  onRestoreOwnership: () => void
}

const FileToolbar: React.FC<FileToolbarProps> = ({
  currentPath,
  parentHref,
  serverId,
  isLoadingFiles,
  createArchiveMutation,
  populateServerMutation,
  restoreOwnershipMutation,
  onNavigateToParent,
  onRefresh,
  onUpload,
  onCreateFile,
  onCompressServer,
  onReplaceServerFiles,
  onRestoreOwnership,
}) => {
  return (
    <>
      {currentPath !== '/' && (
        <ButtonLink variant="outline" to={parentHref} onClick={(event) => {
          if (event.defaultPrevented || event.button !== 0
            || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return
          event.preventDefault()
          onNavigateToParent()
        }}>
          <ArrowUp className="mr-2 h-4 w-4" />
          返回上级
        </ButtonLink>
      )}

      {currentPath === '/' && (
        <>
          <FileSnapshotActions
            serverId={serverId}
            path="/"
            isServerMode={true}
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
    </>
  )
}

export default FileToolbar
