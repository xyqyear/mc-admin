import React, { useState, useRef, useCallback } from 'react'
import { toast } from 'sonner'
import {
  Upload,
  Trash2,
  FileArchive,
  HelpCircle,
} from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Alert, AlertTitle, AlertDescription } from '@/components/ui/alert'
import { Spinner } from '@/components/ui/spinner'
import { Switch } from '@/components/ui/switch'
import { Progress } from '@/components/ui/progress'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog'

import SHA256HelpModal from '@/components/modals/SHA256HelpModal'
import { useArchiveMutations } from '@/hooks/mutations/useArchiveMutations'
import { formatUtils } from '@/utils/serverUtils'

interface ArchiveUploadDialogProps {
  open: boolean
  onClose: () => void
  /** Pre-populated files from drag-and-drop */
  initialFiles?: File[]
}

const ArchiveUploadDialog: React.FC<ArchiveUploadDialogProps> = ({
  open,
  onClose,
  initialFiles,
}) => {
  const { useUploadFile } = useArchiveMutations()
  const uploadFileMutation = useUploadFile()

  const [uploadFiles, setUploadFiles] = useState<File[]>([])
  const [allowOverwrite, setAllowOverwrite] = useState(false)
  const [sha256HelpVisible, setSha256HelpVisible] = useState(false)

  // Upload progress tracking
  const [uploadProgress, setUploadProgress] = useState(0)
  const [uploadSpeed, setUploadSpeed] = useState('0 B/s')
  const [isUploading, setIsUploading] = useState(false)
  const uploadBytesHistory = useRef<Array<{ time: number; bytes: number }>>([])
  const uploadAbortController = useRef<AbortController | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  // Sync initial files when dialog opens with drag-drop files
  const prevInitialFilesRef = useRef<File[] | undefined>(undefined)
  if (open && initialFiles && initialFiles !== prevInitialFilesRef.current) {
    prevInitialFilesRef.current = initialFiles
    // Use functional setter to avoid stale closure; this runs during render
    // which is fine since it's guarded by the ref check
    setUploadFiles(initialFiles)
  }
  if (!open && prevInitialFilesRef.current) {
    prevInitialFilesRef.current = undefined
  }

  const calculateSpeed = (loadedBytes: number): string => {
    const now = Date.now()
    const history = uploadBytesHistory.current
    history.push({ time: now, bytes: loadedBytes })
    const fiveSecondsAgo = now - 5000
    uploadBytesHistory.current = history.filter(point => point.time >= fiveSecondsAgo)
    if (uploadBytesHistory.current.length < 2) return '0 B/s'
    const oldest = uploadBytesHistory.current[0]
    const newest = uploadBytesHistory.current[uploadBytesHistory.current.length - 1]
    const timeDiff = (newest.time - oldest.time) / 1000
    const bytesDiff = newest.bytes - oldest.bytes
    if (timeDiff <= 0) return '0 B/s'
    const speed = bytesDiff / timeDiff
    return `${formatUtils.formatBytes(speed)}/s`
  }

  const resetProgress = () => {
    uploadAbortController.current = null
    setIsUploading(false)
    uploadBytesHistory.current = []
    setUploadProgress(0)
    setUploadSpeed('0 B/s')
  }

  const handleUploadWithProgress = async (file: File) => {
    const controller = new AbortController()
    uploadAbortController.current = controller
    setIsUploading(true)
    uploadBytesHistory.current = []
    setUploadProgress(0)
    setUploadSpeed('0 B/s')

    try {
      await uploadFileMutation.mutateAsync({
        path: '/',
        file,
        allowOverwrite,
        options: {
          signal: controller.signal,
          onUploadProgress: (progressEvent) => {
            const percent = Math.round(progressEvent.progress)
            setUploadProgress(percent)
            setUploadSpeed(calculateSpeed(progressEvent.loaded))
          },
        },
      })
      resetProgress()
    } catch (error: any) {
      resetProgress()
      if (error.name === 'CanceledError' || error.code === 'ERR_CANCELED') return
      throw error
    }
  }

  const cleanup = useCallback(() => {
    if (uploadAbortController.current) {
      uploadAbortController.current.abort()
      uploadAbortController.current = null
    }
    setUploadFiles([])
    setAllowOverwrite(false)
    setUploadProgress(0)
    setUploadSpeed('0 B/s')
    setIsUploading(false)
    uploadBytesHistory.current = []
    onClose()
  }, [onClose])

  const hasValidFiles = uploadFiles.some(file => {
    const name = file.name.toLowerCase()
    return name.endsWith('.zip') || name.endsWith('.7z')
  })

  const handleStartUpload = async () => {
    const validFiles = uploadFiles.filter(file => {
      const name = file.name.toLowerCase()
      return name.endsWith('.zip') || name.endsWith('.7z')
    })
    if (validFiles.length === 0) {
      toast.warning('请选择要上传的压缩包文件')
      return
    }
    for (const file of validFiles) {
      await handleUploadWithProgress(file)
    }
    cleanup()
  }

  const handleFileInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || [])
    const validFiles = files.filter(f => {
      const name = f.name.toLowerCase()
      return name.endsWith('.zip') || name.endsWith('.7z')
    })
    const invalidFiles = files.filter(f => {
      const name = f.name.toLowerCase()
      return !name.endsWith('.zip') && !name.endsWith('.7z')
    })
    if (invalidFiles.length > 0) {
      toast.error(`${invalidFiles.map(f => f.name).join(', ')} 不是支持的格式，只支持 .zip 和 .7z`)
    }
    if (validFiles.length > 0) {
      setUploadFiles(prev => [...prev, ...validFiles])
    }
    e.target.value = ''
  }

  return (
    <>
      <Dialog open={open} onOpenChange={(o) => { if (!o) cleanup() }}>
        <DialogContent className="sm:max-w-md" showCloseButton={false}>
          <DialogHeader>
            <DialogTitle>上传文件</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <input
                ref={fileInputRef}
                type="file"
                accept=".zip,.7z"
                multiple
                className="hidden"
                onChange={handleFileInputChange}
              />
              <Button
                variant="outline"
                onClick={() => fileInputRef.current?.click()}
              >
                <Upload className="mr-2 h-4 w-4" />
                选择压缩包文件
              </Button>
            </div>

            {uploadFiles.length > 0 && (
              <div className="space-y-1">
                {uploadFiles.map((file, i) => (
                  <div key={i} className="flex items-center justify-between text-sm p-2 bg-muted/50 rounded">
                    <div className="flex items-center gap-2 min-w-0">
                      <FileArchive className="h-4 w-4 text-yellow-500 shrink-0" />
                      <span className="truncate">{file.name}</span>
                    </div>
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      onClick={() => setUploadFiles(prev => prev.filter((_, idx) => idx !== i))}
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                ))}
              </div>
            )}

            <p className="text-sm text-muted-foreground">
              仅支持 .zip 和 .7z 格式的压缩包文件
            </p>

            <Alert>
              <AlertTitle>
                <div className="flex items-center justify-between">
                  <span>重要提醒</span>
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    onClick={() => setSha256HelpVisible(true)}
                    className="text-orange-600 hover:text-orange-700"
                    title="查看Windows SHA256校验方法"
                  >
                    <HelpCircle className="h-4 w-4" />
                  </Button>
                </div>
              </AlertTitle>
              <AlertDescription>
                上传后请使用SHA256功能核对文件的完整性，确保文件在传输过程中没有损坏。
              </AlertDescription>
            </Alert>

            {isUploading && (
              <div className="space-y-1">
                <Progress value={uploadProgress} />
                <p className="text-sm text-muted-foreground text-right">
                  {uploadProgress}% - {uploadSpeed}
                </p>
              </div>
            )}

            <label className="flex items-center gap-2 cursor-pointer">
              <Switch
                checked={allowOverwrite}
                onCheckedChange={setAllowOverwrite}
              />
              <span className="text-sm">允许覆盖同名文件</span>
            </label>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={cleanup}>
              关闭
            </Button>
            <Button
              onClick={handleStartUpload}
              disabled={!hasValidFiles || isUploading || uploadFileMutation.isPending}
            >
              {(isUploading || uploadFileMutation.isPending) && <Spinner className="mr-2 size-4" />}
              开始上传
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <SHA256HelpModal
        open={sha256HelpVisible}
        onCancel={() => setSha256HelpVisible(false)}
      />
    </>
  )
}

export default ArchiveUploadDialog
