import React from 'react'
import { GitCompareArrows, Loader2 } from 'lucide-react'
import { useNavigate } from 'react-router-dom'

import { Button } from '@/components/ui/button'
import { Alert, AlertTitle, AlertDescription } from '@/components/ui/alert'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
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

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onCancel()}>
      <DialogContent className="sm:max-w-200">
        <DialogHeader>
          <DialogTitle>编辑文件: {editingFile?.name}</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
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
        <DialogFooter>
          <Button
            variant="outline"
            onClick={onShowDiff}
            disabled={!originalFileContent || fileContent === originalFileContent}
          >
            <GitCompareArrows className="mr-2 h-4 w-4" />
            差异对比
          </Button>
          <Button variant="outline" onClick={onCancel}>
            取消
          </Button>
          <Button onClick={onSave} disabled={confirmLoading}>
            {confirmLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            保存
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export default FileEditModal
