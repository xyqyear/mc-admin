import { afterEach, expect, it, vi } from 'vitest'
import { readEventStream } from './eventStream'

afterEach(() => vi.restoreAllMocks())

function streamResponse(chunks: string[]) {
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(new TextEncoder().encode(chunk))
      controller.close()
    },
  })
  const response = new Response(stream)
  const reader = stream.getReader()
  const cancel = vi.spyOn(reader, 'cancel')
  const release = vi.spyOn(reader, 'releaseLock')
  vi.spyOn(stream, 'getReader').mockReturnValue(reader)
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(response)
  return { cancel, release }
}

it('skips malformed JSON while dispatching valid events split across chunks', async () => {
  const { cancel, release } = streamResponse(['data: {bad}\n\ndata: {"value":', '1}\n\ndata: {"value":2}\n\n'])
  const events: unknown[] = []
  const close = vi.fn()
  const error = vi.fn()
  await readEventStream({ url: '/players/profiles/stream', onEvent: event => events.push(event), onClose: close, onError: error })
  expect(events).toEqual([{ value: 1 }, { value: 2 }])
  expect(close).toHaveBeenCalledOnce()
  expect(error).not.toHaveBeenCalled()
  expect(cancel).toHaveBeenCalledOnce()
  expect(release).toHaveBeenCalledOnce()
})

it.each([Error, SyntaxError])('reports a callback %s once and stops dispatch without reporting normal close', async (Failure) => {
  const { cancel, release } = streamResponse(['data: {"event_type":"profile"}\n\ndata: {"event_type":"complete"}\n\n'])
  const events: unknown[] = []
  const close = vi.fn()
  const error = vi.fn()
  await readEventStream({
    url: '/players/profiles/stream',
    onEvent: event => { events.push(event); throw new Failure('资料处理失败') },
    onClose: close,
    onError: error,
  })
  expect(events).toEqual([{ event_type: 'profile' }])
  expect(error).toHaveBeenCalledOnce()
  expect(error.mock.calls[0][0]).toBe('资料处理失败')
  expect(error.mock.calls[0][1].name).toBe('ApiError')
  expect(close).not.toHaveBeenCalled()
  expect(cancel).toHaveBeenCalledOnce()
  expect(release).toHaveBeenCalledOnce()
})

it('aborts without a failure or close callback and releases the reader', async () => {
  const ctrl = new AbortController()
  const { cancel, release } = streamResponse(['data: {"value":1}\n\n'])
  const close = vi.fn()
  const error = vi.fn()
  await readEventStream({ url: '/players/profiles/stream', signal: ctrl.signal, onEvent: () => ctrl.abort(), onClose: close, onError: error })
  expect(error).not.toHaveBeenCalled()
  expect(close).not.toHaveBeenCalled()
  expect(cancel).toHaveBeenCalledOnce()
  expect(release).toHaveBeenCalledOnce()
})
