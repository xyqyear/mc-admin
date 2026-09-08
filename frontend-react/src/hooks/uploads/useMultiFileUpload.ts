import { useCallback, useEffect, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { fileApi, type FileStructureItem, type MultiFileUploadResult, type OverwriteConflict, type OverwritePolicy } from '@/hooks/api/fileApi'
import { queryKeys } from '@/utils/api'

export const FILES_PER_BATCH = 1000

interface UploadState {
  step: 'select' | 'checking' | 'conflicts' | 'uploading' | 'complete'
  files: File[]
  conflicts: OverwriteConflict[]
  overwritePolicy?: OverwritePolicy
  uploadProgress?: {
    totalProgress: number
    uploadedFiles: number
    totalFiles: number
    totalSize: number
    uploadedSize: number
  }
  results?: MultiFileUploadResult['results']
  error?: string
}
interface PreparedUpload {
  files: File[]
  sessionId: string
}
const initialState = (files: File[] = []): UploadState => ({ step: 'select', files, conflicts: [] })

function buildFileStructure(files: File[]): FileStructureItem[] {
  const structure: FileStructureItem[] = []
  const directories = new Set<string>()
  for (const file of files) {
    const relativePath = file.webkitRelativePath || file.name
    const parts = relativePath.split('/')
    for (let i = 1; i < parts.length; i += 1) {
      const path = parts.slice(0, i).join('/')
      if (!directories.has(path)) {
        directories.add(path)
        structure.push({ path, name: parts[i - 1], type: 'directory' })
      }
    }
    structure.push({ path: relativePath, name: file.name, type: 'file', size: file.size })
  }
  return structure
}

export function useMultiFileUpload(open: boolean, serverId: string, basePath: string, initialFiles?: File[]) {
  const queryClient = useQueryClient()
  const [uploadState, setUploadState] = useState<UploadState>(initialState)
  const prepared = useRef<PreparedUpload | null>(null)
  const running = useRef<AbortController | null>(null)
  const mounted = useRef(false)

  const dispose = useCallback(() => {
    running.current?.abort()
    running.current = null
    prepared.current = null
  }, [])
  const close = useCallback(() => {
    dispose()
    setUploadState(initialState())
  }, [dispose])
  useEffect(() => {
    mounted.current = true
    return () => { mounted.current = false; dispose() }
  }, [dispose])
  useEffect(() => {
    close()
  }, [open, serverId, basePath, close])
  useEffect(() => {
    if (!open) return
    if (running.current || prepared.current) {
      toast.info('请完成或关闭当前上传后再选择文件')
      return
    }
    setUploadState(initialState(initialFiles))
  }, [open, initialFiles, serverId, basePath])

  const execute = async (checking: boolean) => {
    if (running.current || !mounted.current) return
    if (!checking && (!prepared.current || !uploadState.overwritePolicy)) return
    const files = checking ? [...uploadState.files] : prepared.current!.files
    if (!files.length) return
    const controller = new AbortController()
    running.current = controller
    const signal = controller.signal
    const current = () => mounted.current && running.current === controller
    const ensureCurrent = () => {
      if (!current() || signal.aborted) throw new DOMException('Aborted', 'AbortError')
    }
    const update = (patch: Partial<UploadState>) => {
      if (current() && !signal.aborted) setUploadState(prev => ({ ...prev, ...patch }))
    }
    const totalSize = files.reduce((total, file) => total + file.size, 0)
    let wrote = false
    try {
      let policy = uploadState.overwritePolicy
      if (checking) {
        update({ step: 'checking', error: undefined, conflicts: [], overwritePolicy: undefined })
        const response = await fileApi.checkUploadConflicts(serverId, basePath, { files: buildFileStructure(files) }, signal)
        ensureCurrent()
        prepared.current = { files, sessionId: response.session_id }
        if (response.conflicts.length) {
          update({ step: 'conflicts', conflicts: response.conflicts })
          return
        }
        policy = { mode: 'always_overwrite' }
      }
      const sessionId = prepared.current!.sessionId
      update({ step: 'uploading', uploadProgress: { totalProgress: 0, uploadedFiles: 0, totalFiles: files.length, totalSize, uploadedSize: 0 } })
      await fileApi.setUploadPolicy(serverId, sessionId, policy!, files.length > FILES_PER_BATCH, signal)
      ensureCurrent()
      const results: MultiFileUploadResult['results'] = {}
      let completedBytes = 0
      for (let offset = 0; offset < files.length; offset += FILES_PER_BATCH) {
        ensureCurrent()
        const batch = files.slice(offset, offset + FILES_PER_BATCH)
        const batchBytes = batch.reduce((sum, file) => sum + file.size, 0)
        wrote = true
        const result = await fileApi.uploadFileBatch(serverId, sessionId, basePath, batch, progress => {
          const fraction = progress.total > 0 ? progress.loaded / progress.total : 0
          const uploadedSize = completedBytes + batchBytes * fraction
          const totalProgress = totalSize > 0 ? Math.round(uploadedSize * 100 / totalSize) : Math.round((offset + batch.length * fraction) * 100 / files.length)
          update({ uploadProgress: { totalProgress, uploadedFiles: offset, totalFiles: files.length, totalSize, uploadedSize } })
        }, signal)
        ensureCurrent()
        Object.assign(results, result.results)
        completedBytes += batchBytes
        const totalProgress = totalSize > 0 ? Math.round(completedBytes * 100 / totalSize) : Math.round((offset + batch.length) * 100 / files.length)
        update({ uploadProgress: { totalProgress, uploadedFiles: offset + batch.length, totalFiles: files.length, totalSize, uploadedSize: completedBytes } })
      }
      prepared.current = null
      update({ step: 'complete', results })
      toast.success(`上传完成！成功: ${Object.values(results).filter(result => result.status === 'success').length}/${files.length}`)
    } catch (error) {
      if (!current()) return
      prepared.current = null
      const message = signal.aborted ? '上传已取消，已写入的文件会保留' : (error as Error).message || '上传失败'
      setUploadState(prev => ({ ...initialState(prev.files), error: message }))
      if (signal.aborted) toast.info(message)
      else toast.error(message)
    } finally {
      if (running.current === controller) running.current = null
      if (wrote) await queryClient.invalidateQueries({ queryKey: queryKeys.files.lists(serverId) })
    }
  }
  return {
    uploadState,
    totalSize: uploadState.files.reduce((total, file) => total + file.size, 0),
    check: () => execute(true),
    start: () => execute(false),
    setPolicy: (overwritePolicy: OverwritePolicy) => setUploadState(prev => ({ ...prev, overwritePolicy })),
    cancel: () => running.current?.abort(),
    close,
    back: () => {
      if (running.current) return
      prepared.current = null
      setUploadState(prev => initialState(prev.files))
    },
  }
}
