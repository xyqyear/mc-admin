import { useCallback, useEffect, useRef, useState } from 'react'
import { createSHA256 } from 'hash-wasm'
import { toast } from 'sonner'
import { useQueryClient } from '@tanstack/react-query'
import { archiveApi, type ArchiveSHA256Event } from '@/hooks/api/archiveApi'
import { queryKeys } from '@/utils/api'
import { readEventStream } from '@/utils/eventStream'
import { formatUtils } from '@/utils/serverUtils'

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

interface UploadView {
  phase: UploadPhase
  progress: number
  speed: string
  statusText: string
  detailText: string
  retryState: RetryState | null
}

const emptyView = (): UploadView => ({
  phase: 'idle', progress: 0, speed: '0 B/s', statusText: '', detailText: '', retryState: null,
})
const isArchive = (file: File) => /\.(zip|7z)$/i.test(file.name)

export function useArchiveUpload(open: boolean, initialFiles?: File[]) {
  const queryClient = useQueryClient()
  const [uploadFiles, setUploadFiles] = useState<File[]>([])
  const [allowOverwrite, setAllowOverwrite] = useState(false)
  const [view, setView] = useState<UploadView>(emptyView)
  const mounted = useRef(false)
  const activeUpload = useRef<ActiveUpload | null>(null)
  const queue = useRef<File[]>([])
  const index = useRef(0)
  const runner = useRef<AbortController | null>(null)
  const pending = useRef<Promise<void> | null>(null)
  const action = useRef(0)
  const retryAction = useRef<(() => void) | null>(null)

  const dispose = useCallback(() => {
    action.current += 1
    runner.current?.abort()
    runner.current = null
    retryAction.current = null
    const uploadId = activeUpload.current?.uploadId
    activeUpload.current = null
    if (uploadId) void archiveApi.cancelArchiveUpload(uploadId).catch(() => undefined)
    queue.current = []
    index.current = 0
  }, [])

  const close = useCallback(() => {
    dispose()
    setUploadFiles([])
    setAllowOverwrite(false)
    setView(emptyView())
  }, [dispose])

  useEffect(() => {
    mounted.current = true
    return () => { mounted.current = false; dispose() }
  }, [dispose])

  useEffect(() => {
    if (!open) { close(); return }
    if (!initialFiles) return
    if (runner.current || queue.current.length > 0) {
      toast.warning('请完成或关闭当前上传后再选择文件')
      return
    }
    setUploadFiles(initialFiles.filter(isArchive))
    setView(emptyView())
  }, [open, initialFiles, close])

  const runQueue = async () => {
    if (runner.current || !queue.current.length || !mounted.current) return
    const controller = new AbortController()
    runner.current = controller
    const signal = controller.signal
    const check = () => {
      if (!mounted.current || runner.current !== controller || signal.aborted) {
        throw new DOMException('Aborted', 'AbortError')
      }
    }
    const update = (patch: Partial<UploadView>) => {
      if (mounted.current && runner.current === controller && !signal.aborted) {
        setView(prev => ({ ...prev, ...patch }))
      }
    }
    const waitForRetry = (fileName: string, attempt: number, error: unknown) => {
      check()
      const delay = getRetryDelayMs(attempt)
      const started = Date.now()
      update({ phase: 'retrying', statusText: `网络波动，等待重试 ${fileName}` })
      return new Promise<void>((resolve, reject) => {
        const tick = () => {
          const remainingSeconds = Math.ceil(Math.max(0, delay - (Date.now() - started)) / 1000)
          update({ retryState: { attempt, remainingSeconds, message: errorMessage(error) }, detailText: `将在 ${remainingSeconds} 秒后自动重试` })
        }
        const finish = () => { cleanup(); resolve() }
        const abort = () => { cleanup(); reject(new DOMException('Aborted', 'AbortError')) }
        const timeout = window.setTimeout(finish, delay)
        const interval = window.setInterval(tick, RETRY_TICK_MS)
        const cleanup = () => {
          window.clearTimeout(timeout)
          window.clearInterval(interval)
          signal.removeEventListener('abort', abort)
          if (retryAction.current === finish) retryAction.current = null
          update({ retryState: null })
        }
        retryAction.current = finish
        signal.addEventListener('abort', abort, { once: true })
        tick()
      })
    }
    const request = async <T,>(fileName: string, text: string, operation: () => Promise<T>, sessionRequired = false, phase: UploadPhase = 'uploading'): Promise<T> => {
      let attempt = 0
      while (true) {
        check()
        update({ phase, statusText: text })
        try {
          const result = await operation()
          check()
          return result
        } catch (error) {
          check()
          if (isCanceled(error)) throw error
          if (sessionRequired && getErrorStatus(error) === 404) throw createUploadSessionExpiredError()
          if (!shouldRetry(error)) throw error
          await waitForRetry(fileName, ++attempt, error)
        }
      }
    }

    try {
      for (; index.current < queue.current.length; index.current += 1) {
        check()
        const file = queue.current[index.current]
        let active = activeUpload.current
        if (active) {
          const status = await request(file.name, `恢复 ${file.name}`, () => archiveApi.getArchiveUploadStatus(active!.uploadId, signal), true)
          active.offset = status.offset
          active.chunkSize = status.chunkSize || active.chunkSize
        } else {
          const upload = await request(file.name, `准备上传 ${file.name}`, async () => {
            const result = await archiveApi.initArchiveUpload({ path: ROOT_ARCHIVE_PATH, filename: file.name, size: file.size, allow_overwrite: allowOverwrite }, signal)
            if (signal.aborted || runner.current !== controller) {
              void archiveApi.cancelArchiveUpload(result.upload_id).catch(() => undefined)
            }
            return result
          })
          active = { uploadId: upload.upload_id, file, offset: upload.offset, chunkSize: upload.chunk_size || DEFAULT_CHUNK_SIZE }
          activeUpload.current = active
        }
        const current = active
        const started = Date.now()
        const initialOffset = current.offset
        const reportProgress = () => {
          const seconds = Math.max((Date.now() - started) / 1000, 0.001)
          update({ progress: Math.round(current.offset * 100 / file.size), speed: `${formatUtils.formatBytes((current.offset - initialOffset) / seconds)}/s`, detailText: `${formatUtils.formatBytes(current.offset)} / ${formatUtils.formatBytes(file.size)}` })
        }
        reportProgress()
        while (current.offset < file.size) {
          const chunk = file.slice(current.offset, Math.min(current.offset + current.chunkSize, file.size))
          try {
            const response = await request(file.name, `上传 ${file.name} (${index.current + 1}/${queue.current.length})`, () => archiveApi.uploadArchiveChunk(current.uploadId, current.offset, chunk, signal), true)
            current.offset = response.offset
            current.path = response.path ?? current.path
          } catch (error) {
            if (getErrorStatus(error) !== 409) throw error
            const status = await request(file.name, `同步上传进度 ${file.name}`, () => archiveApi.getArchiveUploadStatus(current.uploadId, signal), true)
            current.offset = status.offset
          }
          reportProgress()
        }
        update({ phase: 'verifying', progress: 0, speed: '0 B/s', statusText: `校验 ${file.name}`, detailText: '本地 0% / 服务器 0%' })
        const verification: VerifyProgress = { local: 0, server: 0 }
        const reportVerification = (side: keyof VerifyProgress, percent: number) => {
          verification[side] = percent
          update({ progress: Math.round((verification.local + verification.server) / 2), detailText: `本地 ${Math.round(verification.local)}% / 服务器 ${Math.round(verification.server)}%` })
        }
        const [localHash, serverHash] = await Promise.all([
          hashLocalFile(file, DEFAULT_CHUNK_SIZE, signal, percent => reportVerification('local', percent)),
          hashServerUpload(current.uploadId, signal, percent => reportVerification('server', percent)),
        ])
        check()
        if (localHash !== serverHash) throw new Error('SHA256 校验失败，服务器文件与本地文件不一致')
        const verified = await request(file.name, `发布 ${file.name}`, () => archiveApi.verifyArchiveUpload(current.uploadId, { sha256: localHash }, signal), true, 'verifying')
        current.path = verified.path
        activeUpload.current = null
        await queryClient.invalidateQueries({ queryKey: queryKeys.archive.files(ROOT_ARCHIVE_PATH) })
        check()
      }
      queue.current = []
      index.current = 0
      update({ phase: 'complete', progress: 100, statusText: '上传完成', detailText: '所有压缩包已上传并通过 SHA256 校验' })
      toast.success('文件上传并校验成功')
    } catch (error) {
      if (isCanceled(error) || signal.aborted || runner.current !== controller) return
      const expired = isUploadSessionExpiredError(error)
      const message = expired ? UPLOAD_SESSION_EXPIRED_MESSAGE : errorMessage(error)
      update({ phase: 'error', statusText: expired ? '上传会话已过期' : '上传失败', detailText: message, retryState: null })
      const uploadId = activeUpload.current?.uploadId
      activeUpload.current = null
      queue.current = []
      index.current = 0
      if (uploadId) void archiveApi.cancelArchiveUpload(uploadId).catch(() => undefined)
      toast.error(`上传失败: ${message}`)
    } finally {
      controller.abort()
      if (runner.current === controller) runner.current = null
    }
  }

  const start = () => {
    if (runner.current || !uploadFiles.length) return
    action.current += 1
    queue.current = [...uploadFiles]
    index.current = 0
    pending.current = runQueue()
  }
  const pause = () => {
    action.current += 1
    runner.current?.abort()
    setView(prev => ({ ...prev, phase: 'paused', retryState: null, statusText: '已暂停' }))
  }
  const resume = async () => {
    const ticket = ++action.current
    setView(prev => ({ ...prev, phase: 'uploading', retryState: null }))
    await pending.current
    if (!mounted.current || action.current !== ticket || !queue.current.length) return
    pending.current = runQueue()
  }
  const canEditFiles = view.phase === 'idle' || view.phase === 'complete' || view.phase === 'error'
  const addFiles = (files: File[]) => {
    if (runner.current || queue.current.length) return
    const valid = files.filter(isArchive)
    if (valid.length !== files.length) toast.error('只支持 .zip 和 .7z 格式的压缩包')
    if (!valid.length) return
    setUploadFiles(prev => view.phase === 'complete' || view.phase === 'error' ? valid : [...prev, ...valid])
    setView(emptyView())
  }
  const removeFile = (fileIndex: number) => {
    if (runner.current || queue.current.length) return
    setUploadFiles(prev => prev.filter((_, i) => i !== fileIndex))
  }
  return {
    ...view, uploadFiles, allowOverwrite, setAllowOverwrite, addFiles, removeFile,
    hasValidFiles: uploadFiles.length > 0,
    isWorking: view.phase === 'uploading' || view.phase === 'retrying' || view.phase === 'verifying',
    canResume: view.phase === 'paused', canDismissByOutside: view.phase === 'idle', canEditFiles,
    start, pause, resume, close, retryNow: () => retryAction.current?.(),
  }
}
