import React, { useCallback, useEffect, useRef, useState } from 'react'
import { createSHA256 } from 'hash-wasm'
import { toast } from 'sonner'
import {
  CheckCircle2,
  FileArchive,
  Pause,
  Play,
  RefreshCcw,
  Trash2,
  Upload,
  XCircle,
} from 'lucide-react'
import { useQueryClient } from '@tanstack/react-query'

import { Button } from '@/components/ui/button'
import { Alert, AlertAction, AlertDescription, AlertTitle } from '@/components/ui/alert'
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
import { archiveApi, type ArchiveSHA256Event } from '@/hooks/api/archiveApi'
import { queryKeys } from '@/utils/api'
import { readEventStream } from '@/utils/eventStream'
import { formatUtils } from '@/utils/serverUtils'

interface ArchiveUploadDialogProps {
  open: boolean
  onClose: () => void
  initialFiles?: File[]
}

type UploadPhase =
  | 'idle'
  | 'uploading'
  | 'retrying'
  | 'paused'
  | 'verifying'
  | 'complete'
  | 'error'

interface ActiveUpload {
  uploadId: string
  file: File
  offset: number
  chunkSize: number
  path?: string
}

interface VerifyProgress {
  local: number
  server: number
}

interface RetryState {
  attempt: number
  remainingSeconds: number
  message: string
}

const ROOT_ARCHIVE_PATH = '/'
const DEFAULT_CHUNK_SIZE = 8 * 1024 * 1024
const INITIAL_RETRY_DELAY_MS = 1000
const MAX_RETRY_DELAY_MS = 10000
const RETRY_TICK_MS = 250
const RETRY_BACKOFF_POWER_CAP = Math.ceil(
  Math.log2(MAX_RETRY_DELAY_MS / INITIAL_RETRY_DELAY_MS),
)
const UPLOAD_SESSION_EXPIRED_MESSAGE = '上传会话已过期，请重新选择压缩包后重新上传。'

const isCanceled = (error: unknown) => {
  const err = error as { name?: string; code?: string }
  return err.name === 'AbortError' || err.name === 'CanceledError' || err.code === 'ERR_CANCELED'
}

const shouldRetry = (error: unknown) => {
  const err = error as { status?: number; code?: string }
  if (err.code === 'ERR_CANCELED') return false
  if (!err.status) return true
  return err.status === 408 || err.status === 429 || err.status >= 500
}

const getErrorStatus = (error: unknown) => (error as { status?: number }).status

const getRetryDelayMs = (attempt: number) => {
  const power = Math.min(Math.max(attempt - 1, 0), RETRY_BACKOFF_POWER_CAP)
  return Math.min(INITIAL_RETRY_DELAY_MS * 2 ** power, MAX_RETRY_DELAY_MS)
}

interface UploadSessionExpiredError extends Error {
  uploadSessionExpired: true
}

const createUploadSessionExpiredError = (): UploadSessionExpiredError =>
  Object.assign(new Error(UPLOAD_SESSION_EXPIRED_MESSAGE), {
    uploadSessionExpired: true as const,
  })

const isUploadSessionExpiredError = (
  error: unknown,
): error is UploadSessionExpiredError =>
  (error as { uploadSessionExpired?: boolean }).uploadSessionExpired === true

const errorMessage = (error: unknown) => {
  const err = error as { message?: unknown }
  if (typeof err.message === 'string') return err.message
  if (err.message && typeof err.message === 'object') {
    const message = (err.message as { message?: unknown }).message
    if (typeof message === 'string') return message
  }
  return '未知错误'
}

async function hashLocalFile(
  file: File,
  chunkSize: number,
  signal: AbortSignal,
  onProgress: (percent: number) => void,
): Promise<string> {
  const hasher = await createSHA256()
  hasher.init()

  let offset = 0
  while (offset < file.size) {
    if (signal.aborted) throw new DOMException('Aborted', 'AbortError')
    const nextOffset = Math.min(offset + chunkSize, file.size)
    const buffer = await file.slice(offset, nextOffset).arrayBuffer()
    if (signal.aborted) throw new DOMException('Aborted', 'AbortError')
    hasher.update(new Uint8Array(buffer))
    offset = nextOffset
    onProgress((offset / file.size) * 100)
  }

  return hasher.digest('hex') as string
}

function hashServerUpload(
  uploadId: string,
  signal: AbortSignal,
  onProgress: (percent: number) => void,
): Promise<string> {
  return new Promise((resolve, reject) => {
    let settled = false
    const handleAbort = () => {
      if (!settled) {
        settled = true
        reject(new DOMException('Aborted', 'AbortError'))
      }
    }
    signal.addEventListener('abort', handleAbort, { once: true })
    const finish = (callback: () => void) => {
      if (settled) return
      settled = true
      signal.removeEventListener('abort', handleAbort)
      callback()
    }
    if (signal.aborted) {
      handleAbort()
      return
    }
    void readEventStream<ArchiveSHA256Event>({
      url: `/archive/upload/${encodeURIComponent(uploadId)}/sha256/stream`,
      method: 'GET',
      signal,
      onEvent: (event) => {
        if (event.event_type === 'error') {
          finish(() => reject(new Error(event.message || 'SHA256 calculation failed')))
          return
        }
        if (event.percent !== undefined) {
          onProgress(event.percent)
        }
        const sha256 = event.sha256
        if (event.event_type === 'complete' && sha256) {
          finish(() => resolve(sha256))
        }
      },
      onError: (message) => {
        finish(() => reject(new Error(message)))
      },
      onClose: () => {
        finish(() => reject(new Error('SHA256 stream closed before completion')))
      },
    })
  })
}

const ArchiveUploadDialog: React.FC<ArchiveUploadDialogProps> = ({
  open,
  onClose,
  initialFiles,
}) => {
  const queryClient = useQueryClient()
  const [uploadFiles, setUploadFiles] = useState<File[]>([])
  const [allowOverwrite, setAllowOverwrite] = useState(false)
  const [phase, setPhase] = useState<UploadPhase>('idle')
  const [progress, setProgress] = useState(0)
  const [speed, setSpeed] = useState('0 B/s')
  const [statusText, setStatusText] = useState('')
  const [detailText, setDetailText] = useState('')
  const [retryState, setRetryState] = useState<RetryState | null>(null)
  const [, setVerifyProgress] = useState<VerifyProgress>({ local: 0, server: 0 })

  const fileInputRef = useRef<HTMLInputElement>(null)
  const activeUploadRef = useRef<ActiveUpload | null>(null)
  const requestAbortRef = useRef<AbortController | null>(null)
  const retryTimeoutRef = useRef<number | null>(null)
  const retryIntervalRef = useRef<number | null>(null)
  const retryNowRef = useRef<(() => void) | null>(null)
  const pausedRef = useRef(false)
  const currentFileIndexRef = useRef(0)
  const bytesHistoryRef = useRef<Array<{ time: number; bytes: number }>>([])

  useEffect(() => {
    if (!open) return
    if (initialFiles) {
      setUploadFiles(initialFiles)
    }
  }, [initialFiles, open])

  const calculateSpeed = (loadedBytes: number): string => {
    const now = Date.now()
    const history = bytesHistoryRef.current
    history.push({ time: now, bytes: loadedBytes })
    const fiveSecondsAgo = now - 5000
    bytesHistoryRef.current = history.filter(point => point.time >= fiveSecondsAgo)
    if (bytesHistoryRef.current.length < 2) return '0 B/s'
    const oldest = bytesHistoryRef.current[0]
    const newest = bytesHistoryRef.current[bytesHistoryRef.current.length - 1]
    const timeDiff = (newest.time - oldest.time) / 1000
    const bytesDiff = newest.bytes - oldest.bytes
    if (timeDiff <= 0) return '0 B/s'
    return `${formatUtils.formatBytes(bytesDiff / timeDiff)}/s`
  }

  const clearRetryWait = useCallback(() => {
    if (retryTimeoutRef.current !== null) {
      window.clearTimeout(retryTimeoutRef.current)
      retryTimeoutRef.current = null
    }
    if (retryIntervalRef.current !== null) {
      window.clearInterval(retryIntervalRef.current)
      retryIntervalRef.current = null
    }
    retryNowRef.current = null
    setRetryState(null)
  }, [])

  const resetState = useCallback(() => {
    requestAbortRef.current?.abort()
    requestAbortRef.current = null
    clearRetryWait()
    pausedRef.current = false
    activeUploadRef.current = null
    currentFileIndexRef.current = 0
    bytesHistoryRef.current = []
    setUploadFiles([])
    setAllowOverwrite(false)
    setPhase('idle')
    setProgress(0)
    setSpeed('0 B/s')
    setStatusText('')
    setDetailText('')
    setRetryState(null)
    setVerifyProgress({ local: 0, server: 0 })
  }, [clearRetryWait])

  const cancelActiveUpload = useCallback(() => {
    const uploadId = activeUploadRef.current?.uploadId
    if (uploadId) {
      void archiveApi.cancelArchiveUpload(uploadId).catch(() => undefined)
    }
  }, [])

  const cleanup = useCallback(() => {
    requestAbortRef.current?.abort()
    if (activeUploadRef.current) {
      cancelActiveUpload()
    }
    resetState()
    onClose()
  }, [cancelActiveUpload, onClose, resetState])

  const validFiles = uploadFiles.filter(file => {
    const name = file.name.toLowerCase()
    return name.endsWith('.zip') || name.endsWith('.7z')
  })

  const hasValidFiles = validFiles.length > 0
  const isWorking = phase === 'uploading' || phase === 'retrying' || phase === 'verifying'
  const canResume = phase === 'paused' && hasValidFiles
  const canDismissByOutside = phase === 'idle'
  const canEditFiles = !activeUploadRef.current && (
    phase === 'idle' || phase === 'complete' || phase === 'error'
  )

  const updateUploadProgress = (file: File, loaded: number) => {
    const percent = Math.round((loaded * 100) / file.size)
    setProgress(percent)
    setSpeed(calculateSpeed(loaded))
    setDetailText(`${formatUtils.formatBytes(loaded)} / ${formatUtils.formatBytes(file.size)}`)
  }

  const updateVerifyProgress = (next: Partial<VerifyProgress>) => {
    setVerifyProgress(prev => {
      const merged = { ...prev, ...next }
      setProgress(Math.round((merged.local + merged.server) / 2))
      setDetailText(`本地 ${Math.round(merged.local)}% / 服务器 ${Math.round(merged.server)}%`)
      return merged
    })
  }

  const waitForRetry = useCallback((
    fileName: string,
    attempt: number,
    delayMs: number,
    error: unknown,
  ): Promise<void> => {
    clearRetryWait()
    const controller = new AbortController()
    requestAbortRef.current = controller
    const message = errorMessage(error)
    const startedAt = Date.now()

    const updateCountdown = () => {
      const remainingMs = Math.max(0, delayMs - (Date.now() - startedAt))
      const remainingSeconds = Math.ceil(remainingMs / 1000)
      setRetryState({ attempt, remainingSeconds, message })
      setDetailText(`将在 ${remainingSeconds} 秒后自动重试`)
    }

    setPhase('retrying')
    setStatusText(`网络波动，等待重试 ${fileName}`)
    updateCountdown()

    return new Promise((resolve, reject) => {
      let settled = false
      const settle = (result: 'retry' | 'abort') => {
        if (settled) return
        settled = true
        clearRetryWait()
        if (requestAbortRef.current === controller) {
          requestAbortRef.current = null
        }
        if (result === 'retry') {
          resolve()
          return
        }
        reject(new DOMException('Aborted', 'AbortError'))
      }

      retryNowRef.current = () => settle('retry')
      retryIntervalRef.current = window.setInterval(updateCountdown, RETRY_TICK_MS)
      retryTimeoutRef.current = window.setTimeout(() => settle('retry'), delayMs)
      controller.signal.addEventListener('abort', () => settle('abort'), { once: true })
    })
  }, [clearRetryWait])

  const runRetriableUploadRequest = async <T,>(
    fileName: string,
    actionText: string,
    operation: (signal: AbortSignal) => Promise<T>,
    sessionRequired = false,
    requestPhase: UploadPhase = 'uploading',
  ): Promise<T> => {
    let attempt = 0
    while (true) {
      if (pausedRef.current) {
        throw new DOMException('Aborted', 'AbortError')
      }

      setPhase(requestPhase)
      setStatusText(actionText)
      const controller = new AbortController()
      requestAbortRef.current = controller

      try {
        return await operation(controller.signal)
      } catch (error) {
        if (isCanceled(error)) throw error
        if (sessionRequired && getErrorStatus(error) === 404) {
          throw createUploadSessionExpiredError()
        }
        if (!shouldRetry(error)) throw error

        attempt += 1
        await waitForRetry(fileName, attempt, getRetryDelayMs(attempt), error)
      } finally {
        if (requestAbortRef.current === controller) {
          requestAbortRef.current = null
        }
      }
    }
  }

  const getOrCreateUpload = async (file: File): Promise<ActiveUpload> => {
    const active = activeUploadRef.current
    if (active && active.file === file) {
      const status = await runRetriableUploadRequest(
        file.name,
        `恢复 ${file.name}`,
        (signal) => archiveApi.getArchiveUploadStatus(active.uploadId, signal),
        true,
      )
      active.offset = status.offset
      active.chunkSize = status.chunkSize || active.chunkSize
      return active
    }

    const upload = await runRetriableUploadRequest(
      file.name,
      `准备上传 ${file.name}`,
      (signal) => archiveApi.initArchiveUpload({
        path: ROOT_ARCHIVE_PATH,
        filename: file.name,
        size: file.size,
        allow_overwrite: allowOverwrite,
      }, signal),
    )
    const next = {
      uploadId: upload.upload_id,
      file,
      offset: upload.offset,
      chunkSize: upload.chunk_size || DEFAULT_CHUNK_SIZE,
    }
    activeUploadRef.current = next
    return next
  }

  const uploadFile = async (file: File, index: number, totalFiles: number) => {
    setPhase('uploading')
    setStatusText(`上传 ${file.name} (${index + 1}/${totalFiles})`)
    bytesHistoryRef.current = []
    updateUploadProgress(file, activeUploadRef.current?.offset ?? 0)

    let active: ActiveUpload
    try {
      active = await getOrCreateUpload(file)
    } catch (error) {
      if (isCanceled(error) && pausedRef.current) {
        setPhase('paused')
        setStatusText(`已暂停 ${file.name}`)
        return false
      }
      throw error
    }
    updateUploadProgress(file, active.offset)

    let uploadedPath: string | undefined = active.path
    while (active.offset < file.size) {
      if (pausedRef.current) {
        setPhase('paused')
        setStatusText(`已暂停 ${file.name}`)
        return false
      }

      const chunk = file.slice(
        active.offset,
        Math.min(active.offset + active.chunkSize, file.size),
      )

      try {
        const response = await runRetriableUploadRequest(
          file.name,
          `上传 ${file.name} (${index + 1}/${totalFiles})`,
          (signal) => archiveApi.uploadArchiveChunk(
            active.uploadId,
            active.offset,
            chunk,
            signal,
          ),
          true,
        )
        active.offset = response.offset
        uploadedPath = response.path ?? uploadedPath
        updateUploadProgress(file, active.offset)
      } catch (error) {
        if (isCanceled(error) && pausedRef.current) {
          setPhase('paused')
          setStatusText(`已暂停 ${file.name}`)
          return false
        }
        if (getErrorStatus(error) === 409) {
          const serverStatus = await runRetriableUploadRequest(
            file.name,
            `同步上传进度 ${file.name}`,
            (signal) => archiveApi.getArchiveUploadStatus(active.uploadId, signal),
            true,
          )
          active.offset = serverStatus.offset
          updateUploadProgress(file, active.offset)
          continue
        }

        throw error
      }
    }

    if (!uploadedPath) {
      uploadedPath = `/${file.name}`
    }
    active.path = uploadedPath
    await verifyFile(file, active)
    activeUploadRef.current = null
    return true
  }

  const verifyFile = async (file: File, active: ActiveUpload) => {
    const controller = new AbortController()
    requestAbortRef.current = controller
    setPhase('verifying')
    setProgress(0)
    setSpeed('0 B/s')
    setVerifyProgress({ local: 0, server: 0 })
    setStatusText(`校验 ${file.name}`)
    setDetailText('本地 0% / 服务器 0%')

    try {
      const [localHash, serverHash] = await Promise.all([
        hashLocalFile(file, DEFAULT_CHUNK_SIZE, controller.signal, (percent) => {
          updateVerifyProgress({ local: percent })
        }),
        hashServerUpload(active.uploadId, controller.signal, (percent) => {
          updateVerifyProgress({ server: percent })
        }),
      ])
      if (localHash !== serverHash) {
        await runRetriableUploadRequest(
          file.name,
          `清理 ${file.name}`,
          (signal) => archiveApi.verifyArchiveUpload(
            active.uploadId,
            { sha256: localHash },
            signal,
          ),
          true,
          'verifying',
        ).catch(() => undefined)
        throw new Error('SHA256 校验失败，服务器文件与本地文件不一致')
      }
      const verified = await runRetriableUploadRequest(
        file.name,
        `发布 ${file.name}`,
        (signal) => archiveApi.verifyArchiveUpload(
          active.uploadId,
          { sha256: localHash },
          signal,
        ),
        true,
        'verifying',
      )
      active.path = verified.path
      setProgress(100)
      setDetailText('SHA256 校验通过')
      await queryClient.invalidateQueries({ queryKey: queryKeys.archive.files(ROOT_ARCHIVE_PATH) })
    } finally {
      if (requestAbortRef.current === controller) {
        requestAbortRef.current = null
      }
    }
  }

  const runUploadQueue = async (startIndex: number) => {
    if (!hasValidFiles) {
      toast.warning('请选择要上传的压缩包文件')
      return
    }

    pausedRef.current = false
    try {
      for (let i = startIndex; i < validFiles.length; i += 1) {
        currentFileIndexRef.current = i
        const completed = await uploadFile(validFiles[i], i, validFiles.length)
        if (!completed) return
      }
      setPhase('complete')
      setStatusText('上传完成')
      setDetailText('所有压缩包已上传并通过 SHA256 校验')
      setProgress(100)
      toast.success('文件上传并校验成功')
    } catch (error) {
      if (isCanceled(error)) return
      clearRetryWait()
      if (activeUploadRef.current) {
        cancelActiveUpload()
        activeUploadRef.current = null
      }
      pausedRef.current = false
      const message = isUploadSessionExpiredError(error)
        ? UPLOAD_SESSION_EXPIRED_MESSAGE
        : errorMessage(error)
      setPhase('error')
      setStatusText(isUploadSessionExpiredError(error) ? '上传会话已过期' : '上传失败')
      setDetailText(message)
      toast.error(`上传失败: ${message}`)
    }
  }

  const handleStartUpload = async () => {
    await runUploadQueue(activeUploadRef.current ? currentFileIndexRef.current : 0)
  }

  const handlePause = () => {
    pausedRef.current = true
    clearRetryWait()
    const currentFile = validFiles[currentFileIndexRef.current]
    setPhase('paused')
    setStatusText(currentFile ? `已暂停 ${currentFile.name}` : '已暂停')
    requestAbortRef.current?.abort()
  }

  const handleResume = () => {
    pausedRef.current = false
    setRetryState(null)
    void runUploadQueue(currentFileIndexRef.current)
  }

  const handleRetryNow = () => {
    retryNowRef.current?.()
  }

  const handleFileInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || [])
    const nextValidFiles = files.filter(f => {
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
    if (nextValidFiles.length > 0) {
      const shouldResetFinishedUpload = phase === 'complete' || phase === 'error'
      setUploadFiles(prev => (
        shouldResetFinishedUpload ? nextValidFiles : [...prev, ...nextValidFiles]
      ))
      if (shouldResetFinishedUpload) {
        clearRetryWait()
        activeUploadRef.current = null
        currentFileIndexRef.current = 0
        setPhase('idle')
        setProgress(0)
        setStatusText('')
        setDetailText('')
      }
    }
    e.target.value = ''
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
                    onClick={() => setUploadFiles(prev => prev.filter((_, idx) => idx !== i))}
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
