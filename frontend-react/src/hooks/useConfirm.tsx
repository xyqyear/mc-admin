import { useState, useCallback } from 'react'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'

interface ConfirmOptions {
  title: string
  description?: string
  confirmText?: string
  cancelText?: string
  variant?: 'default' | 'destructive'
  onConfirm: () => void | Promise<void>
}

export function useConfirm() {
  const [options, setOptions] = useState<ConfirmOptions | null>(null)
  const [loading, setLoading] = useState(false)

  const confirm = useCallback((opts: ConfirmOptions) => {
    setOptions(opts)
  }, [])

  const handleConfirm = async () => {
    if (!options) return
    setLoading(true)
    try {
      await options.onConfirm()
    } finally {
      setLoading(false)
      setOptions(null)
    }
  }

  const ConfirmDialog = () => (
    <AlertDialog open={!!options} onOpenChange={(open) => !open && !loading && setOptions(null)}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{options?.title}</AlertDialogTitle>
          {options?.description && (
            <AlertDialogDescription>{options.description}</AlertDialogDescription>
          )}
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel disabled={loading}>
            {options?.cancelText || 'Cancel'}
          </AlertDialogCancel>
          <AlertDialogAction
            onClick={handleConfirm}
            disabled={loading}
            variant={options?.variant === 'destructive' ? 'destructive' : 'default'}
          >
            {loading ? 'Processing...' : (options?.confirmText || 'Confirm')}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )

  return { confirm, ConfirmDialog }
}
