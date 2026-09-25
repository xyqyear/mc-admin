import { describe, expect, it, vi } from 'vitest'
import { withCleanup } from '../../browser/cleanup'

describe('browser journey cleanup evidence', () => {
  it('preserves the original failure and records all cleanup failures without skipping later cleanup', async () => {
    const original = new Error('History remained running after 60 seconds')
    const proxyError = new Error('Proxy close failed')
    const fileError = new Error('DELETE files returned 500')
    const cleanups: string[] = []
    const error = await withCleanup(
      async () => { throw original },
      { label: 'proxy', run: async () => { cleanups.push('proxy'); throw proxyError } },
      { label: 'marker', run: async () => { cleanups.push('marker'); throw fileError } },
      { label: 'remaining resources', run: async () => { cleanups.push('remaining resources') } },
    ).catch(error => error)
    expect(cleanups).toEqual(['proxy', 'marker', 'remaining resources'])
    expect(error).toBeInstanceOf(AggregateError)
    expect(error.cause).toBe(original)
    expect(error.errors).toEqual([original, proxyError, fileError])
    expect(error.message).toContain(original.stack)
    expect(error.message).toContain(proxyError.stack)
    expect(error.message).toContain(fileError.stack)
    expect(error.message.indexOf(original.message)).toBeLessThan(error.message.indexOf(proxyError.message))
  })

  it('rethrows an original error unchanged after successful cleanup', async () => {
    const original = new Error('Restore did not finalize')
    const cleanup = vi.fn(async () => {})
    await expect(withCleanup(async () => { throw original }, { label: 'marker', run: cleanup })).rejects.toBe(original)
    expect(cleanup).toHaveBeenCalledOnce()
  })

  it('fails an otherwise successful journey when cleanup fails', async () => {
    const failure = new Error('Restore server state returned 500')
    await expect(withCleanup(async () => 'passed', { label: 'server state', run: async () => { throw failure } })).rejects.toBe(failure)
  })

  it('preserves the body result only after every cleanup has completed', async () => {
    const order: string[] = []
    const result = await withCleanup(async () => { order.push('body'); return 'result' },
      { label: 'first', run: async () => { await Promise.resolve(); order.push('first') } },
      { label: 'second', run: async () => { order.push('second') } },
    )
    expect(order).toEqual(['body', 'first', 'second'])
    expect(result).toBe('result')
  })
})
