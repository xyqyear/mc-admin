import React, { useState, useEffect } from 'react'
import { Loader2 } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

interface CreateModalProps {
  open: boolean
  onCancel: () => void
  onSubmit: (values: { fileType: string; fileName: string }) => void
  confirmLoading: boolean
}

const CreateModal: React.FC<CreateModalProps> = ({
  open,
  onCancel,
  onSubmit,
  confirmLoading
}) => {
  const [fileType, setFileType] = useState('file')
  const [fileName, setFileName] = useState('')
  const [error, setError] = useState('')

  useEffect(() => {
    if (open) {
      setFileType('file')
      setFileName('')
      setError('')
    }
  }, [open])

  const validate = (): boolean => {
    if (!fileName.trim()) {
      setError('请输入文件名')
      return false
    }
    if (/[<>:"/\\|?*]/.test(fileName)) {
      setError('文件名包含非法字符')
      return false
    }
    setError('')
    return true
  }

  const handleSubmit = () => {
    if (validate()) {
      onSubmit({ fileType, fileName })
    }
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onCancel()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>新建文件/文件夹</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <div className="space-y-2">
            <Label>类型</Label>
            <Select
              value={fileType}
              onValueChange={(v) => v && setFileType(v)}
              itemToStringLabel={(v) => v === 'file' ? '文件' : v === 'directory' ? '文件夹' : v}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="file">文件</SelectItem>
                <SelectItem value="directory">文件夹</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <Label>名称</Label>
            <Input
              placeholder="输入文件名或文件夹名"
              value={fileName}
              onChange={(e) => {
                setFileName(e.target.value)
                if (error) setError('')
              }}
              onKeyDown={(e) => e.key === 'Enter' && handleSubmit()}
            />
            {error && <p className="text-sm text-destructive">{error}</p>}
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onCancel}>
            取消
          </Button>
          <Button onClick={handleSubmit} disabled={confirmLoading}>
            {confirmLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            创建
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export default CreateModal
