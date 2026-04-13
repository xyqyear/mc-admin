import React, { useState, useEffect } from 'react'
import { Loader2 } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Field, FieldError, FieldLabel } from '@/components/ui/field'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'

interface RenameModalProps {
  open: boolean
  onCancel: () => void
  onSubmit: (newName: string) => void
  initialName?: string
  confirmLoading: boolean
}

const RenameModal: React.FC<RenameModalProps> = ({
  open,
  onCancel,
  onSubmit,
  initialName = '',
  confirmLoading
}) => {
  const [newName, setNewName] = useState(initialName)
  const [error, setError] = useState('')

  useEffect(() => {
    if (open) {
      setNewName(initialName)
      setError('')
    }
  }, [open, initialName])

  const validate = (): boolean => {
    if (!newName.trim()) {
      setError('请输入新名称')
      return false
    }
    if (/[<>:"/\\|?*]/.test(newName)) {
      setError('名称包含非法字符')
      return false
    }
    setError('')
    return true
  }

  const handleSubmit = () => {
    if (validate()) {
      onSubmit(newName)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onCancel()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>重命名</DialogTitle>
        </DialogHeader>
        <Field data-invalid={!!error || undefined}>
          <FieldLabel htmlFor="rename-new-name">新名称</FieldLabel>
          <Input
            id="rename-new-name"
            placeholder="输入新名称"
            value={newName}
            onChange={(e) => {
              setNewName(e.target.value)
              if (error) setError('')
            }}
            onKeyDown={(e) => e.key === 'Enter' && handleSubmit()}
            aria-invalid={!!error || undefined}
            autoFocus
          />
          {error && <FieldError>{error}</FieldError>}
        </Field>
        <DialogFooter>
          <Button variant="outline" onClick={onCancel}>
            取消
          </Button>
          <Button onClick={handleSubmit} disabled={confirmLoading}>
            {confirmLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            确定
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export default RenameModal
