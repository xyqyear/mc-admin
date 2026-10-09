import type { FileDownloadManifestEntry } from '@/features/files/contracts'
import { fileApi } from '@/features/files/api'
import type { ManagedDownloadProgress, ManagedDownloadResult } from '@/features/tasks/downloads'
import { getErrorMessage } from '@/shared/http/api'
import { formatLocalFilenameTimestamp } from '@/shared/utils/formatUtils'

export type DirectoryDownloadLayout = 'flat' | 'original'

export interface DirectoryDownloadOptions {
  paths: string[]
  basePath: string
  layout: DirectoryDownloadLayout
}

interface DestinationEntry {
  source: FileDownloadManifestEntry
  parts: string[]
  warning?: { path: string; destination: string; reason: string }
}

const pathParts = (path: string): string[] => {
  const parts = path.split('/').filter((part) => part !== '' && part !== '.')
  if (parts.includes('..')) throw new Error('下载路径不能超出所选目录')
  return parts
}

export const normalizeDownloadPaths = (paths: string[]): string[] => {
  const selected = new Set(paths.map((path) => pathParts(path).join('/') || '/'))
  return [...selected].sort().filter((path) => {
    if (path !== '/' && selected.has('/')) return false
    const parts = pathParts(path)
    return !parts.some((_, index) => index > 0 && selected.has(parts.slice(0, index).join('/')))
  })
}

const localName = (name: string): string => {
  let safe = [...name].map((character) => {
    const code = character.codePointAt(0) ?? 0
    return code < 32 || /[\\:*?"<>|]/.test(character) ? '_' : character
  }).join('').replace(/[. ]+$/, '_')
  if (/^(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)/i.test(safe)) safe = `_${safe}`
  const encoder = new TextEncoder()
  let length = 0
  safe = [...safe].filter((character) => {
    length += encoder.encode(character).length
    return length <= 200
  }).join('')
  return safe || '_'
}

const duplicateName = (name: string, number: number): string => {
  const dot = name.lastIndexOf('.')
  if (dot > 0 && name.length - dot <= 20) return `${name.slice(0, dot)} (${number})${name.slice(dot)}`
  return `${name} (${number})`
}

export class DirectoryDownloadPathMapper {
  private readonly base: string[]
  private readonly names = new Map<string, Set<string>>()
  private readonly mapped = new Map<string, string[]>()

  constructor(private readonly options: Pick<DirectoryDownloadOptions, 'basePath' | 'layout'>) {
    this.base = pathParts(options.basePath)
  }

  map(entry: FileDownloadManifestEntry): DestinationEntry | undefined {
    const source = pathParts(entry.path)
    if (!this.base.every((part, index) => source[index] === part)) {
      throw new Error('下载清单包含所选目录以外的路径')
    }
    if (entry.type === 'directory' && this.options.layout === 'flat') return undefined
    const relative = source.slice(this.base.length)
    const intended = this.options.layout === 'flat' ? relative.slice(-1) : relative
    if (!intended.length && entry.type === 'file') throw new Error('下载清单中的文件路径无效')
    let destination: string[] = []
    for (let index = 0; index < intended.length; index += 1) {
      const sourceKey = this.options.layout === 'flat' ? source.join('/') : relative.slice(0, index + 1).join('/')
      const existing = this.mapped.get(sourceKey)
      if (existing) {
        destination = existing
        continue
      }
      const parentKey = destination.join('/')
      const used = this.names.get(parentKey) ?? new Set<string>()
      this.names.set(parentKey, used)
      const safe = localName(intended[index])
      let chosen = safe
      let number = 2
      while (used.has(chosen.normalize('NFC').toLowerCase())) chosen = duplicateName(safe, number++)
      used.add(chosen.normalize('NFC').toLowerCase())
      destination = [...destination, chosen]
      this.mapped.set(sourceKey, destination)
    }
    const changed = destination.join('/') !== intended.join('/')
    return {
      source: entry,
      parts: destination,
      warning: changed ? {
        path: entry.path,
        destination: destination.join('/'),
        reason: '已调整重名或本地不支持的文件名，避免覆盖',
      } : undefined,
    }
  }
}

export const getLocalDownloadError = (error: unknown): string => {
  const name = error && typeof error === 'object' && 'name' in error ? error.name : undefined
  switch (name) {
    case 'NotAllowedError': return '没有本地文件夹的写入权限，请重新选择文件夹'
    case 'SecurityError': return '浏览器拒绝访问该文件夹，请选择其他位置'
    case 'NotFoundError': return '本地文件或文件夹已被移动或删除'
    case 'QuotaExceededError': return '本地磁盘空间不足'
    case 'NotReadableError': return '无法读取本地保存目录，请选择其他位置'
    case 'InvalidStateError': return '本地文件写入状态无效，请重新下载'
    case 'NoModificationAllowedError': return '本地文件正在被其他程序占用'
    case 'TypeMismatchError':
    case 'InvalidModificationError': return '本地文件名或目录结构存在冲突'
    case 'AbortError': return '浏览器未允许写入此文件'
    default: return getErrorMessage(error, '文件下载失败')
  }
}

const isMissing = (error: unknown): boolean => error instanceof DOMException && error.name === 'NotFoundError'

export const createExportDirectory = async (
  selected: FileSystemDirectoryHandle,
  serverName: string,
  signal: AbortSignal,
): Promise<FileSystemDirectoryHandle> => {
  const name = `${localName(serverName.replace(/ /g, '_'))}_${formatLocalFilenameTimestamp()}`
  for (let number = 1; ; number += 1) {
    signal.throwIfAborted()
    const candidate = number === 1 ? name : `${name} (${number})`
    try {
      await selected.getDirectoryHandle(candidate)
      continue
    } catch (error) {
      if (!isMissing(error)) {
        if (error instanceof DOMException && error.name === 'TypeMismatchError') continue
        throw error
      }
    }
    try {
      await selected.getFileHandle(candidate)
      continue
    } catch (error) {
      if (!isMissing(error)) throw error
    }
    signal.throwIfAborted()
    return selected.getDirectoryHandle(candidate, { create: true })
  }
}

export const executeDirectoryDownload = async (
  serverId: string,
  selected: FileSystemDirectoryHandle,
  options: DirectoryDownloadOptions,
  report: (progress: ManagedDownloadProgress) => void,
  signal: AbortSignal,
): Promise<ManagedDownloadResult> => {
  let started = 0
  const output = await createExportDirectory(selected, serverId, signal).catch((error: unknown) => {
    if (signal.aborted) throw error
    throw new Error(getLocalDownloadError(error), { cause: error })
  })
  const progress: ManagedDownloadResult = {
    downloadedSize: 0,
    size: 0,
    completedFiles: 0,
    failedFiles: 0,
    totalFiles: 0,
    listingComplete: false,
    destination: `${selected.name}/${output.name}`,
    failures: [],
    warnings: [],
    warningCount: 0,
  }
  const mapper = new DirectoryDownloadPathMapper(options)
  const directories = new Map<string, Promise<FileSystemDirectoryHandle>>([['', Promise.resolve(output)]])
  let generation: number | undefined
  let reportedAt = 0
  const emit = (force = false) => {
    const now = Date.now()
    if (!force && now - reportedAt < 150) return
    reportedAt = now
    progress.speed = progress.listingComplete
      ? (progress.downloadedSize ?? 0) / Math.max((now - started) / 1000, 0.001)
      : undefined
    progress.progress = progress.size
      ? Math.min(99, (progress.downloadedSize ?? 0) / progress.size * 100)
      : 0
    report({ ...progress, failures: [...progress.failures!], warnings: [...progress.warnings!] })
  }
  const fail = (path: string, error: string) => {
    progress.failedFiles += 1
    if (progress.failures!.length < 100) progress.failures!.push({ path, error })
    emit(true)
  }
  const getDirectory = (parts: string[]): Promise<FileSystemDirectoryHandle> => {
    const key = parts.join('/')
    const known = directories.get(key)
    if (known) return known
    const handle = getDirectory(parts.slice(0, -1)).then(async (parent) => {
      signal.throwIfAborted()
      return parent.getDirectoryHandle(parts.at(-1)!, { create: true })
    })
    directories.set(key, handle)
    return handle
  }
  const writeFile = async (entry: DestinationEntry): Promise<void> => {
    let parent: FileSystemDirectoryHandle | undefined
    let response: Response | undefined
    let created = false
    const name = entry.parts.at(-1)!
    try {
      signal.throwIfAborted()
      parent = await getDirectory(entry.parts.slice(0, -1))
      signal.throwIfAborted()
      response = await fileApi.downloadFileStream(serverId, entry.source.path, signal, generation)
      if (!response.body) throw new Error('服务器未返回文件内容')
      signal.throwIfAborted()
      try {
        await parent.getFileHandle(name)
        throw new Error('本地目标文件已存在，未覆盖，请重新下载')
      } catch (error) {
        if (!isMissing(error)) throw error
      }
      const handle = await parent.getFileHandle(name, { create: true })
      created = true
      signal.throwIfAborted()
      const writable = await handle.createWritable()
      let received = 0
      const counted = response.body.pipeThrough(new TransformStream<Uint8Array, Uint8Array>({
        transform(chunk, controller) {
          received += chunk.byteLength
          progress.downloadedSize = (progress.downloadedSize ?? 0) + chunk.byteLength
          emit()
          controller.enqueue(chunk)
        },
        flush() {
          if (received !== entry.source.size) throw new Error('文件在下载期间发生变化，请重新下载')
        },
      }))
      await counted.pipeTo(writable, { signal })
      progress.completedFiles = (progress.completedFiles ?? 0) + 1
      emit(true)
    } catch (error) {
      if (created && parent) await parent.removeEntry(name).catch(() => undefined)
      if (!signal.aborted) fail(entry.source.path, getLocalDownloadError(error))
    } finally {
      await response?.body?.cancel().catch(() => undefined)
    }
  }

  emit(true)
  try {
    signal.throwIfAborted()
    const manifest = await fileApi.getDownloadManifest(serverId, { paths: normalizeDownloadPaths(options.paths) }, signal)
    signal.throwIfAborted()
    generation = manifest.server_generation
    progress.totalFiles = manifest.entries.filter((entry) => entry.type === 'file').length + manifest.errors.length
    progress.size = manifest.entries.reduce((total, entry) => total + entry.size, 0)
    progress.listingComplete = true
    started = Date.now()
    emit(true)
    for (const error of manifest.errors) fail(error.path, error.message)
    const files: DestinationEntry[] = []
    for (const entry of manifest.entries) {
      try {
        signal.throwIfAborted()
        const mapped = mapper.map(entry)
        if (!mapped) continue
        if (mapped.warning) {
          progress.warningCount = (progress.warningCount ?? 0) + 1
          if (progress.warnings!.length < 100) progress.warnings!.push(mapped.warning)
        }
        if (entry.type === 'directory') {
          await getDirectory(mapped.parts)
        } else {
          files.push(mapped)
        }
      } catch (error) {
        if (signal.aborted) throw error
        if (entry.type === 'directory') progress.totalFiles = (progress.totalFiles ?? 0) + 1
        fail(entry.path, getLocalDownloadError(error))
      }
    }
    let next = 0
    const worker = async () => {
      while (!signal.aborted && next < files.length) {
        await writeFile(files[next++])
      }
    }
    await Promise.all(Array.from({ length: Math.min(4, files.length) }, worker))
    signal.throwIfAborted()
    emit(true)
    return progress
  } catch (error) {
    emit(true)
    if (signal.aborted) throw error
    throw new Error(getLocalDownloadError(error), { cause: error })
  }
}
