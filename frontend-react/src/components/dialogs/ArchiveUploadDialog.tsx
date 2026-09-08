import React, { useRef } from 'react'
import { CheckCircle2, FileArchive, Pause, Play, RefreshCcw, Trash2, Upload, XCircle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Alert, AlertAction, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Spinner } from '@/components/ui/spinner'
import { Switch } from '@/components/ui/switch'
import { Progress } from '@/components/ui/progress'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog'
import { useArchiveUpload } from '@/hooks/uploads/useArchiveUpload'

interface ArchiveUploadDialogProps {
  open: boolean
  onClose: () => void
  initialFiles?: File[]
}

const ArchiveUploadDialog: React.FC<ArchiveUploadDialogProps> = ({ open, onClose, initialFiles }) => {
  const fileInputRef = useRef<HTMLInputElement>(null)
  const {
    uploadFiles, allowOverwrite, setAllowOverwrite, phase, progress, speed,
    statusText, detailText, retryState, hasValidFiles, isWorking, canResume,
    canDismissByOutside, canEditFiles, addFiles, removeFile,
    start: handleStartUpload, pause: handlePause, resume: handleResume,
    retryNow: handleRetryNow, close,
  } = useArchiveUpload(open, initialFiles)
  const cleanup = () => { close(); onClose() }
  const handleFileInputChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    addFiles(Array.from(event.target.files || []))
    event.target.value = ''
  }

  return (
    <Dialog
      open={open}
      disablePointerDismissal={!canDismissByOutside}
      onOpenChange={(o, eventDetails) => {
        if (o) return
        if (!canDismissByOutside) {
          eventDetails.cancel()
          return
        }
        cleanup()
      }}
    >
      <DialogContent className="sm:max-w-md" showCloseButton={canDismissByOutside}>
        <DialogHeader>
          <DialogTitle>上传文件</DialogTitle>
        </DialogHeader>
        <div className="flex flex-col gap-4">
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
              disabled={!canEditFiles}
            >
              <Upload data-icon="inline-start" />
              选择压缩包文件
            </Button>
          </div>

          {uploadFiles.length > 0 && (
            <div className="flex flex-col gap-1">
              {uploadFiles.map((file, i) => (
                <div key={`${file.name}-${file.lastModified}-${i}`} className="flex items-center justify-between rounded bg-muted/50 p-2 text-sm">
                  <div className="flex min-w-0 items-center gap-2">
                    <FileArchive className="shrink-0 text-muted-foreground" />
                    <span className="truncate">{file.name}</span>
                  </div>
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    onClick={() => removeFile(i)}
                    disabled={!canEditFiles}
                  >
                    <Trash2 />
                  </Button>
                </div>
              ))}
            </div>
          )}

          <p className="text-sm text-muted-foreground">
            仅支持 .zip 和 .7z 格式的压缩包文件
          </p>

          <Alert>
            {phase === 'complete' ? <CheckCircle2 /> : phase === 'error' ? <XCircle /> : null}
            <AlertTitle>完整性校验</AlertTitle>
            <AlertDescription>
              上传完成后会自动计算本地文件和服务器文件的 SHA256，并在两者一致后标记成功。
            </AlertDescription>
          </Alert>

          {phase !== 'idle' && (
            <div className="flex flex-col gap-1">
              <Progress value={progress} />
              <div className="flex items-center justify-between gap-3 text-sm text-muted-foreground">
                <span className="truncate">{statusText}</span>
                <span className="shrink-0">{progress}%</span>
              </div>
              <p className="text-right text-sm text-muted-foreground">
                {phase === 'uploading' ? `${detailText} - ${speed}` : detailText}
              </p>
            </div>
          )}

          {phase === 'retrying' && retryState && (
            <Alert>
              <RefreshCcw />
              <AlertTitle>等待重试</AlertTitle>
              <AlertDescription>
                第 {retryState.attempt} 次重试将在 {retryState.remainingSeconds} 秒后开始。
                {retryState.message ? ` 原因：${retryState.message}` : ''}
              </AlertDescription>
              <AlertAction>
                <Button size="sm" variant="outline" onClick={handleRetryNow}>
                  <RefreshCcw data-icon="inline-start" />
                  立即重试
                </Button>
              </AlertAction>
            </Alert>
          )}

          <label className="flex cursor-pointer items-center gap-2">
            <Switch
              checked={allowOverwrite}
              onCheckedChange={setAllowOverwrite}
              disabled={!canEditFiles}
            />
            <span className="text-sm">允许覆盖同名文件</span>
          </label>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={cleanup} disabled={isWorking}>
            关闭
          </Button>
          {(phase === 'uploading' || phase === 'retrying') && (
            <Button variant="outline" onClick={handlePause}>
              <Pause data-icon="inline-start" />
              暂停
            </Button>
          )}
          {canResume ? (
            <Button onClick={handleResume}>
              <Play data-icon="inline-start" />
              继续
            </Button>
          ) : (
            <Button
              onClick={handleStartUpload}
              disabled={!hasValidFiles || isWorking || phase === 'complete'}
            >
              {isWorking ? <Spinner data-icon="inline-start" /> : <Upload data-icon="inline-start" />}
              {phase === 'error' ? '重新上传' : '开始上传'}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export default ArchiveUploadDialog
