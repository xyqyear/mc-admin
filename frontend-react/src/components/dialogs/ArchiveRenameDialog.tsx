import React from 'react'
import { Controller, useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Spinner } from '@/components/ui/spinner'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog'
import { Field, FieldLabel, FieldError } from '@/components/ui/field'

import { useArchiveMutations } from '@/hooks/mutations/useArchiveMutations'
import type { ArchiveFileItem } from '@/hooks/api/archiveApi'

const renameSchema = z.object({
  new_name: z
    .string()
    .min(1, '请输入新名称')
    .max(255, '名称不能超过255个字符')
    .regex(/^[^<>:"/\\|?*]+$/, '名称包含非法字符'),
})

type RenameFormData = z.infer<typeof renameSchema>

interface ArchiveRenameDialogProps {
  open: boolean
  file: ArchiveFileItem | null
  onClose: () => void
}

const ArchiveRenameDialog: React.FC<ArchiveRenameDialogProps> = ({
  open,
  file,
  onClose,
}) => {
  const { useRenameItem } = useArchiveMutations()
  const renameItemMutation = useRenameItem()

  const form = useForm<RenameFormData>({
    resolver: zodResolver(renameSchema),
    defaultValues: { new_name: '' },
  })

  // Sync form value when file changes
  const prevFileRef = React.useRef<ArchiveFileItem | null>(null)
  if (file && file !== prevFileRef.current) {
    prevFileRef.current = file
    form.setValue('new_name', file.name)
  }
  if (!file && prevFileRef.current) {
    prevFileRef.current = null
  }

  const handleClose = () => {
    form.reset()
    onClose()
  }

  const handleSubmit = async (values: RenameFormData) => {
    if (!file) return
    try {
      await renameItemMutation.mutateAsync({
        old_path: file.path,
        new_name: values.new_name,
      })
      handleClose()
    } catch {
      // Error is handled by mutation
    }
  }

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) handleClose() }}>
      <DialogContent className="sm:max-w-md" showCloseButton={false}>
        <DialogHeader>
          <DialogTitle>重命名</DialogTitle>
        </DialogHeader>
        <form onSubmit={form.handleSubmit(handleSubmit)}>
          <Field>
            <FieldLabel htmlFor="new_name">新名称</FieldLabel>
            <Controller
              name="new_name"
              control={form.control}
              render={({ field, fieldState }) => (
                <>
                  <Input
                    id="new_name"
                    placeholder="输入新名称"
                    {...field}
                  />
                  {fieldState.error && (
                    <FieldError>{fieldState.error.message}</FieldError>
                  )}
                </>
              )}
            />
          </Field>
          <DialogFooter className="mt-4">
            <Button type="button" variant="outline" onClick={handleClose}>
              取消
            </Button>
            <Button type="submit" disabled={renameItemMutation.isPending}>
              {renameItemMutation.isPending && <Spinner className="mr-2 size-4" />}
              确定
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

export default ArchiveRenameDialog
