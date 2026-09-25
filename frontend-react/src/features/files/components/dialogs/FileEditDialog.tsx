import React from 'react'
import { GitCompareArrows, Loader2 } from 'lucide-react'
import { useNavigate } from 'react-router'

import { Button } from '@/shared/ui/button'
import { Alert, AlertTitle, AlertDescription } from '@/shared/ui/alert'
import { StatusBadge } from '@/shared/components/StatusBadge'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/shared/ui/dialog'
import { SimpleEditor } from '@/shared/editors/index'
import type { FileItem } from '@/features/files/contracts'

interface FileEditDialogProps {
  open: boolean
  onCancel: () => void
  onSave: () => void
  onShowDiff: () => void
  editingFile: FileItem | null
  fileContent: string
  setFileContent: (content: string) => void
  originalFileContent: string
  isLoadingContent: boolean
  contentReady: boolean
  contentError?: string
  onRetry: () => void
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

const FileEditDialog: React.FC<FileEditDialogProps> = ({
  open,
  onCancel,
  onSave,
  onShowDiff,
  editingFile,
  fileContent,
  setFileContent,
  originalFileContent,
  isLoadingContent,
  contentReady,
  contentError,
  onRetry,
  confirmLoading,
  serverId,
  getCurrentFileLanguageConfig
}) => {
  const navigate = useNavigate()

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onCancel()}>
      <DialogContent className="sm:max-w-200">
        <DialogHeader>
          <DialogTitle>编辑文件: {editingFile?.name}</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          {contentError && (
            <Alert variant="destructive">
              <AlertTitle>读取文件失败</AlertTitle>
              <AlertDescription>{contentError}<Button variant="outline" onClick={onRetry}>重试读取</Button></AlertDescription>
            </Alert>
          )}
          <Alert>
            <AlertTitle>文件编辑</AlertTitle>
            <AlertDescription>
              修改文件内容后点击保存。请谨慎编辑配置文件，错误的配置可能导致服务器无法启动。
            </AlertDescription>
          </Alert>
          {isLoadingContent ? (
            <div className="text-center py-8 text-muted-foreground">加载文件内容中...</div>
          ) : (
            (() => {
              const { language, options, config, composeWarning } = getCurrentFileLanguageConfig()
              return (
                <div className="space-y-3">
                  {composeWarning && (
                    <Alert variant={composeWarning.severity === 'error' ? 'destructive' : 'default'}>
                      <AlertTitle>{composeWarning.title}</AlertTitle>
                      <AlertDescription>
                        <div className="space-y-2">
                          <p>{composeWarning.message}</p>
                          <Button
                            variant="link"
                            size="sm"
                            className="p-0 h-auto"
                            onClick={() => navigate(`/server/${serverId}/compose`)}
                          >
                            {composeWarning.linkText}
                          </Button>
                        </div>
                      </AlertDescription>
                    </Alert>
                  )}

                  {config?.supportsValidation && (
                    <div className="text-xs text-muted-foreground px-2">
                      <StatusBadge tone="info">
                        {config?.description} - 支持语法检查
                      </StatusBadge>
                    </div>
                  )}

                  <SimpleEditor
                    height="500px"
                    language={language}
                    value={fileContent}
                    onChange={(value: string | undefined) => value !== undefined && setFileContent(value)}
                    options={{ ...options, readOnly: !contentReady || confirmLoading }}
                  />
                </div>
              )
            })()
          )}
        </div>
        <DialogFooter>
          <Button
            variant="outline"
            onClick={onShowDiff}
            disabled={!contentReady || fileContent === originalFileContent}
          >
            <GitCompareArrows className="mr-2 h-4 w-4" />
            差异对比
          </Button>
          <Button variant="outline" onClick={onCancel} disabled={confirmLoading}>
            取消
          </Button>
          <Button onClick={onSave} disabled={!contentReady || confirmLoading}>
            {confirmLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            保存
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export default FileEditDialog
