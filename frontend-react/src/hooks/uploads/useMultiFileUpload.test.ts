import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useMultiFileUpload, FILES_PER_BATCH } from './useMultiFileUpload'

const mocks = vi.hoisted(() => ({
  checkUploadConflicts: vi.fn(), setUploadPolicy: vi.fn(), uploadFileBatch: vi.fn(), invalidateQueries: vi.fn(),
}))
vi.mock('@/hooks/api/fileApi', () => ({ fileApi: mocks }))
vi.mock('@tanstack/react-query', () => ({ useQueryClient: () => mocks }))
vi.mock('sonner', () => ({ toast: { info: vi.fn(), error: vi.fn(), success: vi.fn() } }))

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>(r => { resolve = r })
  return { promise, resolve }
}
function batchResult(files: File[]) {
  return { message: 'complete', results: Object.fromEntries(files.map(file => [file.name, { status: 'success' }])) }
}

beforeEach(() => {
  vi.clearAllMocks()
  mocks.checkUploadConflicts.mockResolvedValue({ session_id: 'session', conflicts: [] })
  mocks.setUploadPolicy.mockResolvedValue({ message: 'set' })
  mocks.uploadFileBatch.mockImplementation(async (_server: string, _session: string, _path: string, files: File[]) => batchResult(files))
  mocks.invalidateQueries.mockResolvedValue(undefined)
})

describe('ordinary file upload lifecycle', () => {
  it('treats conflict checking as busy and ignores the result after close', async () => {
    const check = deferred<{ session_id: string; conflicts: never[] }>()
    mocks.checkUploadConflicts.mockImplementationOnce(() => check.promise)
    const files = [new File(['content'], 'file.txt')]
    const { result } = renderHook(() => useMultiFileUpload(true, 'server', '/', files))
    act(() => { void result.current.check(); void result.current.check() })
    expect(result.current.uploadState.step).toBe('checking')
    expect(mocks.checkUploadConflicts).toHaveBeenCalledTimes(1)
    act(() => result.current.close())
    expect(mocks.checkUploadConflicts.mock.calls[0][3].aborted).toBe(true)
    await act(async () => { check.resolve({ session_id: 'late', conflicts: [] }) })
    expect(result.current.uploadState.step).toBe('select')
    expect(result.current.uploadState.files).toEqual([])
    expect(mocks.setUploadPolicy).not.toHaveBeenCalled()
  })

  it('chooses reusable with its batch plan and awaits each batch even for zero-byte files', async () => {
    const files = Array.from({ length: FILES_PER_BATCH + 1 }, (_, i) => new File([], `${i}.txt`))
    const first = deferred<ReturnType<typeof batchResult>>()
    mocks.uploadFileBatch.mockImplementationOnce(() => first.promise)
    const { result, rerender } = renderHook(({ selected }) => useMultiFileUpload(true, 'server', '/', selected), { initialProps: { selected: files } })
    act(() => { void result.current.check() })
    await waitFor(() => expect(mocks.uploadFileBatch).toHaveBeenCalledTimes(1))
    expect(mocks.setUploadPolicy.mock.calls[0][3]).toBe(true)
    expect(mocks.uploadFileBatch.mock.calls[0][3]).toHaveLength(FILES_PER_BATCH)
    rerender({ selected: [new File([], 'later.txt')] })
    expect(result.current.uploadState.files).toHaveLength(FILES_PER_BATCH + 1)
    act(() => mocks.uploadFileBatch.mock.calls[0][4]({ loaded: 50, total: 100, percent: 50 }))
    expect(Number.isFinite(result.current.uploadState.uploadProgress?.totalProgress)).toBe(true)
    await act(async () => { first.resolve(batchResult(files.slice(0, FILES_PER_BATCH))) })
    await waitFor(() => expect(result.current.uploadState.step).toBe('complete'))
    expect(mocks.uploadFileBatch.mock.calls.map(call => call[3].length)).toEqual([1000, 1])
    expect(result.current.uploadState.uploadProgress?.uploadedFiles).toBe(1001)
    expect(Object.keys(result.current.uploadState.results!)).toHaveLength(1001)
  })

  it('aborts on unmount, retains completed writes and does not schedule another batch', async () => {
    const files = Array.from({ length: FILES_PER_BATCH + 1 }, (_, i) => new File(['x'], `${i}.txt`))
    const first = deferred<ReturnType<typeof batchResult>>()
    mocks.uploadFileBatch.mockImplementationOnce(() => first.promise)
    const { result, unmount } = renderHook(() => useMultiFileUpload(true, 'server', '/', files))
    act(() => { void result.current.check() })
    await waitFor(() => expect(mocks.uploadFileBatch).toHaveBeenCalledTimes(1))
    unmount()
    expect(mocks.uploadFileBatch.mock.calls[0][5].aborted).toBe(true)
    await act(async () => { first.resolve(batchResult(files.slice(0, FILES_PER_BATCH))) })
    expect(mocks.uploadFileBatch).toHaveBeenCalledTimes(1)
    expect(mocks.invalidateQueries).toHaveBeenCalledTimes(1)
  })
})
