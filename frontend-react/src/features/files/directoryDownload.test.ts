import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { fileApi } from '@/features/files/api'
import { DirectoryDownloadPathMapper, executeDirectoryDownload, normalizeDownloadPaths } from '@/features/files/directoryDownload'
import { getDirectoryDownloadSupport, useDirectoryDownload } from '@/features/files/useDirectoryDownload'
import { useDownloadStore } from '@/features/tasks/downloadStore'
import type { FileDownloadManifestResponse } from '@/features/files/contracts'
import type { ManagedDownloadProgress } from '@/features/tasks/downloads'

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }))

class LocalFile {
  chunks: Uint8Array[] = []
  bytes = new Uint8Array()
  beforeClose?: () => Promise<void>
  get text() { return new TextDecoder().decode(this.bytes) }
  asHandle(): FileSystemFileHandle {
    return {
      createWritable: async () => new WritableStream<Uint8Array>({
        write: (chunk) => { this.chunks.push(chunk.slice()) },
        close: async () => {
          await this.beforeClose?.()
          this.bytes = new Uint8Array(this.chunks.flatMap((chunk) => [...chunk]))
        },
        abort: () => { this.chunks = [] },
      }),
    } as unknown as FileSystemFileHandle
  }
}

class LocalDirectory {
  directories = new Map<string, LocalDirectory>()
  files = new Map<string, LocalFile>()
  constructor(readonly name: string) {}
  async getDirectoryHandle(name: string, options?: { create?: boolean }): Promise<FileSystemDirectoryHandle> {
    if (this.files.has(name)) throw new DOMException('type', 'TypeMismatchError')
    if (!this.directories.has(name)) {
      if (!options?.create) throw new DOMException('missing', 'NotFoundError')
      this.directories.set(name, new LocalDirectory(name))
    }
    return this.directories.get(name)!.asHandle()
  }
  async getFileHandle(name: string, options?: { create?: boolean }): Promise<FileSystemFileHandle> {
    if (this.directories.has(name)) throw new DOMException('type', 'TypeMismatchError')
    if (!this.files.has(name)) {
      if (!options?.create) throw new DOMException('missing', 'NotFoundError')
      this.files.set(name, new LocalFile())
    }
    return this.files.get(name)!.asHandle()
  }
  async removeEntry(name: string): Promise<void> { this.files.delete(name) }
  asHandle(): FileSystemDirectoryHandle { return this as unknown as FileSystemDirectoryHandle }
  export(): LocalDirectory { return [...this.directories.values()][0] }
}

const page = (paths: string[], cursor: string | null = null): FileDownloadManifestResponse => ({
  server_generation: 7, entries: paths.map((path) => ({ path, type: 'file', size: 3 })), errors: [], next_cursor: cursor,
})
const response = (text: string): Response => new Response(new TextEncoder().encode(text))

beforeEach(() => {
  vi.stubGlobal('isSecureContext', true)
  vi.stubGlobal('FileSystemFileHandle', { prototype: { createWritable: vi.fn() } })
  localStorage.clear()
  useDownloadStore.setState({ tasks: [] })
})

afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.useRealTimers() })

describe('directory download layout', () => {
  it('maps flat duplicate and case-insensitive names without overwriting either content', () => {
    const mapper = new DirectoryDownloadPathMapper({ basePath: '/search', layout: 'flat' })
    const names = ['search/a/data.dat', 'search/b/data.dat', 'search/c/DATA.dat'].map((path) => mapper.map({ path, type: 'file', size: 1 }))
    expect(names.map((entry) => entry?.parts.join('/'))).toEqual(['data.dat', 'data (2).dat', 'DATA (3).dat'])
    expect(names[1]?.warning).toMatchObject({ path: 'search/b/data.dat', destination: 'data (2).dat' })
  })

  it('uses the captured root, preserves directories, and reports unsupported local names', () => {
    const mapper = new DirectoryDownloadPathMapper({ basePath: '/search/', layout: 'original' })
    expect(mapper.map({ path: 'search/a/empty', type: 'directory', size: 0 })?.parts).toEqual(['a', 'empty'])
    const restricted = mapper.map({ path: 'search/a/CON.txt', type: 'file', size: 1 })
    expect(restricted?.parts).toEqual(['a', '_CON.txt'])
    expect(restricted?.warning?.path).toBe('search/a/CON.txt')
    expect(mapper.map({ path: 'search/bad:name/a?.txt', type: 'file', size: 1 })?.parts).toEqual(['bad_name', 'a_.txt'])
    expect(() => mapper.map({ path: 'outside/a.txt', type: 'file', size: 1 })).toThrow('所选目录以外')
    expect(() => mapper.map({ path: 'search/../a.txt', type: 'file', size: 1 })).toThrow('超出所选目录')
  })

  it('reduces duplicate and recursive scopes while retaining distinct similarly named directories', () => {
    expect(normalizeDownloadPaths(['/a/x', 'a', '/a/x', 'a-b', 'a-b/x', 'b/x'])).toEqual(['a', 'a-b', 'b/x'])
    expect(normalizeDownloadPaths(['/', '/a'])).toEqual(['/'])
  })
})

describe('streaming directory download', () => {
  it('names exports with the server and local time while preserving same-name files and directories', async () => {
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date(2026, 9, 7, 15, 42, 3, 123))
    const local = new LocalDirectory('chosen')
    const name = '生存服_20261007_154203_123'
    const existing = new LocalFile()
    existing.bytes = new TextEncoder().encode('previous export')
    local.files.set(name, existing)
    local.directories.set(`${name} (2)`, new LocalDirectory(`${name} (2)`))
    vi.spyOn(fileApi, 'getDownloadManifest').mockResolvedValue(page(['file.txt']))
    vi.spyOn(fileApi, 'downloadFileStream').mockResolvedValue(response('new'))
    const result = await executeDirectoryDownload('生存服', local.asHandle(), {
      paths: ['file.txt'], basePath: '/', layout: 'original',
    }, vi.fn(), new AbortController().signal)
    expect(result.destination).toBe(`chosen/${name} (3)`)
    expect(local.directories.get(`${name} (3)`)!.files.get('file.txt')!.text).toBe('new')
    expect(existing.text).toBe('previous export')
    expect(local.directories.get(`${name} (2)`)!.files.size).toBe(0)
  })

  it('streams pages into one separate directory and preserves hierarchy and empty folders', async () => {
    const local = new LocalDirectory('chosen')
    const existing = new LocalFile()
    existing.bytes = new TextEncoder().encode('existing')
    local.files.set('one.txt', existing)
    const manifest = vi.spyOn(fileApi, 'getDownloadManifest')
      .mockResolvedValueOnce({ ...page(['search/a/one.txt'], 'next'), entries: [
        { path: 'search/a/empty', type: 'directory', size: 0 }, { path: 'search/a/one.txt', type: 'file', size: 3 },
      ] })
      .mockResolvedValueOnce(page(['search/b/two.txt']))
    vi.spyOn(fileApi, 'downloadFileStream').mockImplementation(async (_, path) => response(path.endsWith('one.txt') ? 'one' : 'two'))
    const progress: ManagedDownloadProgress[] = []
    const result = await executeDirectoryDownload('s', local.asHandle(), {
      paths: ['/search/a', '/search/b/two.txt'], basePath: '/search', layout: 'original',
    }, (event) => progress.push(event), new AbortController().signal)
    expect(manifest.mock.calls[1][1]).toMatchObject({ cursor: 'next' })
    expect(local.export().directories.get('a')!.files.get('one.txt')!.text).toBe('one')
    expect(local.export().directories.get('b')!.files.get('two.txt')!.text).toBe('two')
    expect(local.export().directories.get('a')!.directories.has('empty')).toBe(true)
    expect(existing.text).toBe('existing')
    expect(result).toMatchObject({ totalFiles: 2, completedFiles: 2, failedFiles: 0, size: 6, downloadedSize: 6, listingComplete: true })
    expect(progress[0].listingComplete).toBe(false)
  })

  it('writes received chunks before the response ends and counts completion after local close', async () => {
    const local = new LocalDirectory('chosen')
    vi.spyOn(fileApi, 'getDownloadManifest').mockResolvedValue({ server_generation: 7, entries: [{ path: 'large.dat', type: 'file', size: 6 }], errors: [], next_cursor: null })
    let network!: ReadableStreamDefaultController<Uint8Array>
    vi.spyOn(fileApi, 'downloadFileStream').mockResolvedValue(new Response(new ReadableStream<Uint8Array>({
      start(controller) { network = controller; controller.enqueue(new TextEncoder().encode('one')) },
    })))
    const reports: ManagedDownloadProgress[] = []
    const pending = executeDirectoryDownload('s', local.asHandle(), {
      paths: ['large.dat'], basePath: '/', layout: 'original',
    }, (event) => reports.push(event), new AbortController().signal)
    await waitFor(() => expect(local.export().files.get('large.dat')?.chunks).toHaveLength(1))
    const file = local.export().files.get('large.dat')!
    let releaseClose!: () => void
    file.beforeClose = () => new Promise<void>((resolve) => { releaseClose = resolve })
    expect(reports.at(-1)?.completedFiles).toBe(0)
    network.enqueue(new TextEncoder().encode('two'))
    network.close()
    await waitFor(() => expect(releaseClose).toBeTypeOf('function'))
    expect(reports.at(-1)?.completedFiles).toBe(0)
    releaseClose()
    expect((await pending).completedFiles).toBe(1)
    expect(file.text).toBe('onetwo')
  })

  it('keeps transfer concurrency at four for a larger page', async () => {
    const local = new LocalDirectory('chosen')
    vi.spyOn(fileApi, 'getDownloadManifest').mockResolvedValue(page(['0', '1', '2', '3', '4', '5']))
    const controllers: ReadableStreamDefaultController<Uint8Array>[] = []
    const stream = vi.spyOn(fileApi, 'downloadFileStream').mockImplementation(async () => new Response(new ReadableStream<Uint8Array>({
      start(controller) { controller.enqueue(new TextEncoder().encode('abc')); controllers.push(controller) },
    })))
    const pending = executeDirectoryDownload('s', local.asHandle(), { paths: ['0', '1', '2', '3', '4', '5'], basePath: '/', layout: 'flat' }, vi.fn(), new AbortController().signal)
    await waitFor(() => expect(stream).toHaveBeenCalledTimes(4))
    expect(controllers).toHaveLength(4)
    controllers[0].close()
    await waitFor(() => expect(stream).toHaveBeenCalledTimes(5))
    controllers[1].close()
    await waitFor(() => expect(stream).toHaveBeenCalledTimes(6))
    controllers.slice(2).forEach((controller) => controller.close())
    expect((await pending).completedFiles).toBe(6)
  })

  it('retains successful files and reports server and source-change failures individually', async () => {
    const local = new LocalDirectory('chosen')
    vi.spyOn(fileApi, 'getDownloadManifest').mockResolvedValue({ ...page(['good', 'changed']), errors: [{ path: 'link', message: '目录链接不能下载' }] })
    vi.spyOn(fileApi, 'downloadFileStream').mockImplementation(async (_, path) => response(path === 'good' ? 'yes' : 'different'))
    const result = await executeDirectoryDownload('s', local.asHandle(), { paths: ['good', 'changed', 'link'], basePath: '/', layout: 'flat' }, vi.fn(), new AbortController().signal)
    expect(result).toMatchObject({ totalFiles: 3, completedFiles: 1, failedFiles: 2 })
    expect(result.failures).toEqual(expect.arrayContaining([
      { path: 'link', error: '目录链接不能下载' }, { path: 'changed', error: '文件在下载期间发生变化，请重新下载' },
    ]))
    expect(local.export().files.get('good')!.text).toBe('yes')
    expect(local.export().files.has('changed')).toBe(false)
  })

  it('saves same-named selected files separately and exposes the flat name mapping', async () => {
    const local = new LocalDirectory('chosen')
    vi.spyOn(fileApi, 'getDownloadManifest').mockResolvedValue(page(['search/a/data.dat', 'search/b/data.dat']))
    vi.spyOn(fileApi, 'downloadFileStream').mockImplementation(async (_, path) => response(path.includes('/a/') ? 'one' : 'two'))
    const result = await executeDirectoryDownload('s', local.asHandle(), {
      paths: ['search/a/data.dat', 'search/b/data.dat'], basePath: '/search', layout: 'flat',
    }, vi.fn(), new AbortController().signal)
    expect(local.export().files.get('data.dat')!.text).toBe('one')
    expect(local.export().files.get('data (2).dat')!.text).toBe('two')
    expect(result).toMatchObject({ completedFiles: 2, warningCount: 1 })
    expect(result.warnings?.[0]).toMatchObject({ path: 'search/b/data.dat', destination: 'data (2).dat' })
  })

  it('stops on server generation changes and binds each content request to its manifest generation', async () => {
    const local = new LocalDirectory('chosen')
    vi.spyOn(fileApi, 'getDownloadManifest')
      .mockResolvedValueOnce(page(['a'], 'next'))
      .mockResolvedValueOnce({ ...page(['b']), server_generation: 8 })
    const stream = vi.spyOn(fileApi, 'downloadFileStream').mockResolvedValue(response('old'))
    await expect(executeDirectoryDownload('s', local.asHandle(), {
      paths: ['a', 'b'], basePath: '/', layout: 'original',
    }, vi.fn(), new AbortController().signal)).rejects.toThrow('服务器实例发生变化')
    expect(stream).toHaveBeenCalledExactlyOnceWith('s', 'a', expect.any(AbortSignal), 7)
    expect(local.export().files.get('a')!.text).toBe('old')
    expect(local.export().files.has('b')).toBe(false)
  })
})

describe('direct download entry and task lifetime', () => {
  it('distinguishes unsupported browsers from insecure Chrome or Edge without versions', () => {
    vi.stubGlobal('showDirectoryPicker', undefined)
    expect(getDirectoryDownloadSupport()).toEqual({ supported: false, reason: '当前浏览器不支持直接下载到文件夹，仅支持 Chrome 和 Edge。' })
    vi.stubGlobal('isSecureContext', false)
    vi.spyOn(navigator, 'userAgent', 'get').mockReturnValue('Mozilla/5.0 Chrome/140.0.0.0')
    expect(getDirectoryDownloadSupport()).toEqual({ supported: false, reason: '此功能需要通过 HTTPS 或 localhost 访问。' })
  })

  it('opens the picker during the click before requests, freezes selection, and continues after unmount', async () => {
    const local = new LocalDirectory('chosen')
    let choose!: (handle: FileSystemDirectoryHandle) => void
    const picker = vi.fn(() => new Promise<FileSystemDirectoryHandle>((resolve) => { choose = resolve }))
    vi.stubGlobal('showDirectoryPicker', picker)
    const manifest = vi.spyOn(fileApi, 'getDownloadManifest').mockResolvedValue(page(['search/file.txt']))
    vi.spyOn(fileApi, 'downloadFileStream').mockResolvedValue(response('abc'))
    const { result, unmount } = renderHook(() => useDirectoryDownload('s'))
    const paths = ['search/file.txt']
    let pending!: Promise<void>
    act(() => { pending = result.current.downloadToDirectory({ paths, basePath: '/search', layout: 'original' }) })
    expect(picker).toHaveBeenCalledWith({ mode: 'readwrite' })
    expect(manifest).not.toHaveBeenCalled()
    paths.push('search/not-selected.txt')
    unmount()
    choose(local.asHandle())
    await pending
    expect(manifest.mock.calls[0][1].paths).toEqual(['search/file.txt'])
    expect(useDownloadStore.getState().tasks[0]).toMatchObject({ status: 'completed', completedFiles: 1, totalFiles: 1 })
  })

  it('cancels active transfers and pending files while keeping completed files', async () => {
    const local = new LocalDirectory('chosen')
    vi.stubGlobal('showDirectoryPicker', vi.fn().mockResolvedValue(local.asHandle()))
    vi.spyOn(fileApi, 'getDownloadManifest').mockResolvedValue(page(['0', '1', '2', '3', '4', '5']))
    const cancelledStreams = vi.fn()
    const stream = vi.spyOn(fileApi, 'downloadFileStream').mockImplementation(async (_, path) => path === '0'
      ? response('yes') : new Response(new ReadableStream<Uint8Array>({ cancel: cancelledStreams })))
    const { result } = renderHook(() => useDirectoryDownload('s'))
    let pending!: Promise<void>
    act(() => { pending = result.current.downloadToDirectory({ paths: ['0', '1', '2', '3', '4', '5'], basePath: '/', layout: 'flat' }) })
    await waitFor(() => expect(useDownloadStore.getState().tasks[0]?.completedFiles).toBe(1))
    await waitFor(() => expect(stream).toHaveBeenCalledTimes(5))
    act(() => useDownloadStore.getState().cancelTask(useDownloadStore.getState().tasks[0].id))
    await act(async () => { await pending })
    expect(stream).toHaveBeenCalledTimes(5)
    expect(cancelledStreams).toHaveBeenCalled()
    expect(local.export().files.size).toBe(1)
    expect(local.export().files.get('0')!.text).toBe('yes')
    expect(useDownloadStore.getState().tasks[0]).toMatchObject({ status: 'cancelled', completedFiles: 1, failedFiles: 0 })
  })

  it('marks persisted in-flight exports cancelled without persisting write handles or controllers', () => {
    useDownloadStore.getState().addTask({ fileName: 'directory', status: 'downloading', progress: 20,
      completedFiles: 2, totalFiles: 5, abortController: new AbortController() })
    const persisted = JSON.parse(localStorage.getItem('download-store')!).state.tasks[0]
    expect(persisted).toMatchObject({ status: 'cancelled', completedFiles: 2, totalFiles: 5 })
    expect(persisted.abortController).toBeUndefined()
  })

  it('shows partial failures as an error while preserving successful local output and counts', async () => {
    const local = new LocalDirectory('chosen')
    vi.stubGlobal('showDirectoryPicker', vi.fn().mockResolvedValue(local.asHandle()))
    vi.spyOn(fileApi, 'getDownloadManifest').mockResolvedValue(page(['good', 'failed']))
    vi.spyOn(fileApi, 'downloadFileStream').mockImplementation(async (_, path) => {
      if (path === 'failed') throw new Error('服务器文件不存在')
      return response('yes')
    })
    const { result } = renderHook(() => useDirectoryDownload('s'))
    await act(async () => result.current.downloadToDirectory({ paths: ['good', 'failed'], basePath: '/', layout: 'original' }))
    expect(useDownloadStore.getState().tasks[0]).toMatchObject({
      status: 'error', totalFiles: 2, completedFiles: 1, failedFiles: 1,
      failures: [{ path: 'failed', error: '服务器文件不存在' }],
    })
    expect(local.export().files.get('good')!.text).toBe('yes')
  })
})
