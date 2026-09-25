import { renderHook, waitFor } from '@testing-library/react'
import { AxiosError } from 'axios'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { api, AUTH_EXPIRED_EVENT } from '@/shared/http/api'
import { useServerQueries } from '@/features/servers/queries'
import { createTestClient, httpResponse } from '@/test/http'
import { TestProviders } from '@/test/TestProviders'

const originalAdapter = api.defaults.adapter
const adapter = vi.fn()
let client: ReturnType<typeof createTestClient>
beforeEach(() => { vi.clearAllMocks(); api.defaults.adapter = adapter; client = createTestClient() })
afterEach(() => { api.defaults.adapter = originalAdapter; client.clear() })

it.each([401, 403, 409, 422, 500])('preserves status %s, readable message and the original structured detail', async status => {
  const detail = status === 422
    ? [{ loc: ['body', 'content'], msg: '参数无效', type: 'value_error' }]
    : { message: '操作被拒绝', offset: 42 }
  adapter.mockImplementation(async config => httpResponse(config, { detail }, status))
  const error = await api.get('/servers/server/files').catch(error => error)
  expect(error.status).toBe(status)
  expect(error.detail).toEqual(detail)
  expect(typeof error.message).toBe('string')
  expect(error.message).toContain(status === 422 ? '参数无效' : '操作被拒绝')
})

it('keeps network and cancellation codes without inventing an HTTP status', async () => {
  adapter.mockRejectedValue(new AxiosError('Network Error', 'ERR_NETWORK'))
  const network = await api.get('/servers/').catch(error => error)
  expect(network).toMatchObject({ status: undefined, code: 'ERR_NETWORK' })
  expect(network.message).toBe('网络连接失败，请检查网络后重试')
  adapter.mockRejectedValue(new AxiosError('canceled', 'ERR_CANCELED'))
  expect(await api.get('/servers/').catch(error => error)).toMatchObject({ code: 'ERR_CANCELED' })
})

it('expires authenticated sessions only for 401, excluding login and session probing', async () => {
  const expired = vi.fn()
  window.addEventListener(AUTH_EXPIRED_EVENT, expired)
  try {
    adapter.mockImplementation(async config => httpResponse(config, { detail: '会话失效' }, 401))
    await api.get('/user/me').catch(() => undefined)
    await api.post('/auth/login').catch(() => undefined)
    expect(expired).not.toHaveBeenCalled()
    await api.get('/servers/').catch(() => undefined)
    expect(expired).toHaveBeenCalledTimes(1)
    adapter.mockImplementation(async config => httpResponse(config, { detail: '权限不足' }, 403))
    await api.get('/servers/').catch(() => undefined)
    expect(expired).toHaveBeenCalledTimes(1)
  } finally { window.removeEventListener(AUTH_EXPIRED_EVENT, expired) }
})

it.each([401, 403, 409, 422, 500, 'network'] as const)('uses normalized errors for runtime retry policy (%s)', async status => {
  adapter.mockImplementation(async config => {
    if (status === 'network') throw new AxiosError('Network Error', 'ERR_NETWORK', config)
    return httpResponse(config, { detail: '暂时不可用' }, status)
  })
  const { result } = renderHook(() => useServerQueries().useServerCpuPercent('server', 'RUNNING', {
    retryDelay: 0, refetchInterval: false,
  }), { wrapper: ({ children }) => <TestProviders client={client}>{children}</TestProviders> })
  await waitFor(() => expect(result.current.isError).toBe(true))
  expect(adapter).toHaveBeenCalledTimes(status === 500 || status === 'network' ? 3 : 1)
})
