import React from 'react'
import { Download, Database, CheckCircle } from 'lucide-react'
import { useNavigate } from 'react-router-dom'

import { Button } from '@/components/ui/button'
import { Separator } from '@/components/ui/separator'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'

interface CompressionResultModalProps {
  open: boolean
  onCancel: () => void
  archiveFilename: string
  message: string
  onDownload: () => void
  downloadLoading: boolean
}

const CompressionResultModal: React.FC<CompressionResultModalProps> = ({
  open,
  onCancel,
  archiveFilename,
  message,
  onDownload,
  downloadLoading
}) => {
  const navigate = useNavigate()

  const handleNavigateToArchives = () => {
    onCancel()
    navigate('/archives')
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onCancel()}>
      <DialogContent className="sm:max-w-125">
        <DialogHeader>
          <DialogTitle>压缩完成</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <div className="text-center space-y-3">
            <CheckCircle className="mx-auto h-12 w-12 text-green-500" />
            <h3 className="text-lg font-semibold text-green-600">压缩包创建成功</h3>
            <div className="space-y-2">
              <div className="text-sm text-muted-foreground">{message}</div>
              <div className="font-mono text-sm bg-muted p-2 rounded-md border">
                {archiveFilename}
              </div>
            </div>
          </div>

          <Separator />

          <div className="text-center space-y-4">
            <div className="text-muted-foreground text-sm">选择下一步操作：</div>
            <div className="flex items-center justify-center gap-3">
              <Button size="lg" onClick={onDownload} disabled={downloadLoading}>
                <Download className="mr-2 h-4 w-4" />
                立即下载
              </Button>
              <Button variant="outline" size="lg" onClick={handleNavigateToArchives}>
                <Database className="mr-2 h-4 w-4" />
                压缩包管理
              </Button>
            </div>
            <div className="text-muted-foreground text-xs">
              压缩包已保存到系统中，您可以随时在压缩包管理界面找到它
            </div>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}

export default CompressionResultModal
