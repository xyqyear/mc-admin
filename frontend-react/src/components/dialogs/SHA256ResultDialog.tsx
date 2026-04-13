import React from 'react'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'

interface SHA256ResultDialogProps {
  open: boolean
  onClose: () => void
  result: { fileName: string; hash: string } | null
}

const SHA256ResultDialog: React.FC<SHA256ResultDialogProps> = ({
  open,
  onClose,
  result,
}) => {
  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) onClose() }}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>文件 SHA256 校验值</DialogTitle>
        </DialogHeader>
        {result && (
          <div className="space-y-2">
            <p className="font-medium text-sm">SHA256 校验值：</p>
            <div className="bg-muted p-3 rounded border font-mono text-sm break-all select-all">
              {result.hash}
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}

export default SHA256ResultDialog
