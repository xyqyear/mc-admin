import React from 'react'
import { MonacoDiffEditor } from '@/components/editors'
import { Button } from '@/components/ui/button'
import { Alert, AlertTitle, AlertDescription } from '@/components/ui/alert'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog'

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
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="sm:max-w-350">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <Alert>
            <AlertTitle>差异对比视图</AlertTitle>
            <AlertDescription>{description}</AlertDescription>
          </Alert>
          <div className="border rounded-md overflow-hidden h-[600px]">
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
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>关闭</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export default ComposeDiffModal
