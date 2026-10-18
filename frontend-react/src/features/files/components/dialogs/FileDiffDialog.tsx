import React from 'react'

import { Button } from '@/shared/ui/button'
import { ButtonLink } from '@/shared/components/ButtonLink'
import { Alert, AlertTitle, AlertDescription } from '@/shared/ui/alert'
import { StatusBadge } from '@/shared/components/StatusBadge'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/shared/ui/dialog'
import { MonacoDiffEditor } from '@/shared/editors/index'

interface FileDiffDialogProps {
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

const FileDiffDialog: React.FC<FileDiffDialogProps> = ({
  open,
  onCancel,
  originalFileContent,
  fileContent,
  serverId,
  getCurrentFileLanguageConfig
}) => {
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onCancel()}>
      <DialogContent className="sm:max-w-350">
        <DialogHeader>
          <DialogTitle>文件差异对比</DialogTitle>
          <DialogDescription>
            左侧为文件原始内容，右侧为当前编辑的内容。高亮显示的是差异部分。
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          {(() => {
            const { composeWarning } = getCurrentFileLanguageConfig()
            return composeWarning && (
              <Alert variant={composeWarning.severity === 'error' ? 'destructive' : 'default'}>
                <AlertTitle>{composeWarning.title}</AlertTitle>
                <AlertDescription>
                  <div className="space-y-2">
                    <p>{composeWarning.message}</p>
                    <ButtonLink
                      variant="link"
                      size="sm"
                      className="p-0 h-auto"
                      to={`/server/${serverId}/compose`}
                    >
                      {composeWarning.linkText}
                    </ButtonLink>
                  </div>
                </AlertDescription>
              </Alert>
            )
          })()}

          <div className="rounded-md border overflow-hidden h-150">
            {(() => {
              const { language, config } = getCurrentFileLanguageConfig()
              return (
                <div className="h-full">
                  {config?.supportsValidation && (
                    <div className="px-3 py-2 bg-muted border-b text-xs text-muted-foreground">
                      <StatusBadge tone="info">
                        {config?.description} - 语法高亮已启用
                      </StatusBadge>
                    </div>
                  )}
                  <MonacoDiffEditor
                    height={config?.supportsValidation ? "570px" : "600px"}
                    language={language}
                    original={originalFileContent}
                    modified={fileContent}
                    originalTitle="文件原始内容"
                    modifiedTitle="当前编辑内容"
                  />
                </div>
              )
            })()}
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onCancel}>
            关闭
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export default FileDiffDialog
