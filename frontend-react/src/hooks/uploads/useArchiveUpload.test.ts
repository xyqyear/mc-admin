import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useArchiveUpload } from './useArchiveUpload'

const mocks = vi.hoisted(() => ({
  initArchiveUpload: vi.fn(), uploadArchiveChunk: vi.fn(), getArchiveUploadStatus: vi.fn(),
  verifyArchiveUpload: vi.fn(), cancelArchiveUpload: vi.fn(), invalidateQueries: vi.fn(),
}))
vi.mock('@/hooks/api/archiveApi', () => ({ archiveApi: mocks }))
vi.mock('@tanstack/react-query', () => ({ useQueryClient: () => mocks }))
vi.mock('sonner', () => ({ toast: { info: vi.fn(), warning: vi.fn(), error: vi.fn(), success: vi.fn() } }))
vi.mock('hash-wasm', () => ({ createSHA256: async () => ({ init() {}, update() {}, digest: () => 'hash' }) }))
vi.mock('@/utils/eventStream', () => ({
  readEventStream: async ({ onEvent }: { onEvent: (event: unknown) => void }) => {
    onEvent({ event_type: 'complete', percent: 100, sha256: 'hash' })
  },
}))

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>(r => { resolve = r })
  return { promise, resolve }
}
function archive(name: string, content = 'abc') {
  const file = new File([content], name)
  const slice = file.slice.bind(file)
  file.slice = (start, end, type) => {
    const blob = slice(start, end, type)
    return Object.assign(blob, { arrayBuffer: async () => new ArrayBuffer(blob.size) })
  }
  return file
}

beforeEach(() => {
  vi.clearAllMocks()
  mocks.initArchiveUpload.mockImplementation(async ({ filename }: { filename: string }) => ({ upload_id: filename, offset: 0, chunk_size: 3 }))
  mocks.uploadArchiveChunk.mockImplementation(async (_id: string, offset: number, chunk: Blob) => ({ offset: offset + chunk.size, complete: true }))
  mocks.verifyArchiveUpload.mockResolvedValue({ path: '/published.zip' })
  mocks.cancelArchiveUpload.mockResolvedValue(undefined)
  mocks.invalidateQueries.mockResolvedValue(undefined)
})
afterEach(() => vi.useRealTimers())

describe('archive upload lifecycle', () => {
  it('owns one serial queue and keeps new drops out of an active run', async () => {
    const chunk = deferred<{ offset: number; complete: boolean }>()
    mocks.uploadArchiveChunk.mockImplementationOnce(() => chunk.promise)
    const files = [archive('first.zip'), archive('second.zip')]
    const { result, rerender } = renderHook(({ selected }) => useArchiveUpload(true, selected), { initialProps: { selected: files } })
    act(() => { result.current.start(); result.current.start() })
    await waitFor(() => expect(mocks.uploadArchiveChunk).toHaveBeenCalledTimes(1))
    rerender({ selected: [archive('later.zip')] })
    expect(result.current.uploadFiles).toEqual(files)
    expect(mocks.initArchiveUpload).toHaveBeenCalledTimes(1)
    await act(async () => { chunk.resolve({ offset: 3, complete: true }) })
    await waitFor(() => expect(result.current.phase).toBe('complete'))
    expect(mocks.initArchiveUpload.mock.calls.map(call => call[0].filename)).toEqual(['first.zip', 'second.zip'])
    expect(mocks.verifyArchiveUpload).toHaveBeenCalledTimes(2)
  })

  it('waits for an aborted request to settle before resuming from the server offset', async () => {
    const chunk = deferred<{ offset: number; complete: boolean }>()
    mocks.uploadArchiveChunk.mockImplementationOnce(() => chunk.promise)
    mocks.getArchiveUploadStatus.mockResolvedValue({ offset: 3, chunkSize: 3 })
    const files = [archive('resume.zip', 'abcdef')]
    const { result } = renderHook(() => useArchiveUpload(true, files))
    act(() => result.current.start())
    await waitFor(() => expect(mocks.uploadArchiveChunk).toHaveBeenCalledTimes(1))
    act(() => { result.current.pause(); void result.current.resume() })
    expect(mocks.uploadArchiveChunk.mock.calls[0][3].aborted).toBe(true)
    expect(mocks.getArchiveUploadStatus).not.toHaveBeenCalled()
    await act(async () => { chunk.resolve({ offset: 3, complete: false }) })
    await waitFor(() => expect(result.current.phase).toBe('complete'))
    expect(mocks.initArchiveUpload).toHaveBeenCalledTimes(1)
    expect(mocks.getArchiveUploadStatus).toHaveBeenCalledTimes(1)
    expect(mocks.uploadArchiveChunk.mock.calls.map(call => call[1])).toEqual([0, 3])
  })

  it('cancels an active session on unmount and ignores late upload completion', async () => {
    const chunk = deferred<{ offset: number; complete: boolean }>()
    mocks.uploadArchiveChunk.mockImplementationOnce(() => chunk.promise)
    const files = [archive('unmount.zip')]
    const { result, unmount } = renderHook(() => useArchiveUpload(true, files))
    act(() => result.current.start())
    await waitFor(() => expect(mocks.uploadArchiveChunk).toHaveBeenCalledTimes(1))
    unmount()
    expect(mocks.uploadArchiveChunk.mock.calls[0][3].aborted).toBe(true)
    expect(mocks.cancelArchiveUpload).toHaveBeenCalledWith('unmount.zip')
    await act(async () => { chunk.resolve({ offset: 3, complete: true }) })
    expect(mocks.verifyArchiveUpload).not.toHaveBeenCalled()
  })

  it('clears both retry timers and closes the session on unmount', async () => {
    vi.useFakeTimers()
    mocks.uploadArchiveChunk.mockRejectedValue({ status: 503, message: 'unavailable' })
    const files = [archive('retry.zip')]
    const { result, unmount } = renderHook(() => useArchiveUpload(true, files))
    await act(async () => { result.current.start() })
    expect(result.current.phase).toBe('retrying')
    expect(vi.getTimerCount()).toBe(2)
    unmount()
    expect(vi.getTimerCount()).toBe(0)
    expect(mocks.cancelArchiveUpload).toHaveBeenCalledWith('retry.zip')
    await act(async () => { await vi.advanceTimersByTimeAsync(20000) })
    expect(mocks.uploadArchiveChunk).toHaveBeenCalledTimes(1)
  })

  it('keeps a reopened upload independent of a paused run finishing late', async () => {
    const chunk = deferred<{ offset: number; complete: boolean }>()
    mocks.uploadArchiveChunk.mockImplementationOnce(() => chunk.promise)
    const { result, rerender } = renderHook(({ open, files }) => useArchiveUpload(open, files), {
      initialProps: { open: true, files: [archive('old.zip')] },
    })
    act(() => result.current.start())
    await waitFor(() => expect(mocks.uploadArchiveChunk).toHaveBeenCalledTimes(1))
    act(() => { result.current.pause(); result.current.close() })
    rerender({ open: false, files: [] })
    rerender({ open: true, files: [archive('new.zip')] })
    act(() => result.current.start())
    await waitFor(() => expect(result.current.phase).toBe('complete'))
    await act(async () => { chunk.resolve({ offset: 3, complete: true }) })
    expect(result.current.phase).toBe('complete')
    expect(result.current.uploadFiles[0].name).toBe('new.zip')
    expect(mocks.verifyArchiveUpload).toHaveBeenCalledTimes(1)
    expect(mocks.verifyArchiveUpload.mock.calls[0][0]).toBe('new.zip')
    expect(mocks.cancelArchiveUpload).toHaveBeenCalledWith('old.zip')
  })
})
