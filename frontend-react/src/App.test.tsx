import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { AxiosError } from 'axios'
import type { ReactNode } from 'react'
import { api } from '@/shared/http/api'
import { createTestClient, httpResponse } from '@/test/http'
import { TestProviders } from '@/test/TestProviders'
import App from '@/App'

vi.mock('@/app/layout/MainLayout', () => ({ MainLayout: ({ children }: { children: ReactNode }) => <main>{children}</main> }))
vi.mock('@/app/version/VersionUpdateDialog', () => ({ default: () => null }))
vi.mock('@/app/version/useVersionCheck', () => ({ useVersionCheck: () => ({ shouldShowDialog: false }) }))
vi.mock('@/features/users/LoginScreen', () => ({ default: () => <div>登录页面</div> }))
vi.mock('@/app/overview/Overview', () => ({ default: () => <div>服务器总览</div> }))

const originalAdapter = api.defaults.adapter
let client: ReturnType<typeof createTestClient>
const adapter = vi.fn()
beforeEach(() => {
  vi.clearAllMocks(); api.defaults.adapter = adapter; client = createTestClient()
  client.setDefaultOptions({ queries: { retryDelay: 0, gcTime: Infinity } })
})
afterEach(() => { api.defaults.adapter = originalAdapter; client.clear() })
function showApp() { render(<TestProviders client={client} route="/overview"><App /></TestProviders>) }

it.each([401, 403])('shows login for an unauthenticated session (%s)', async status => {
  adapter.mockImplementation(async config => httpResponse(config, { detail: '无法访问' }, status))
  showApp()
  expect(await screen.findByText('登录页面')).toBeTruthy()
  expect(screen.queryByText('服务器总览')).toBeNull()
  expect(adapter.mock.calls.length).toBeLessThanOrEqual(2)
})

it.each([500, 'network'] as const)('retains the protected route and permits retry after a temporary session lookup failure (%s)', async status => {
  adapter.mockImplementation(async config => {
    if (status === 'network') throw new AxiosError('Network Error', 'ERR_NETWORK', config)
    return httpResponse(config, { detail: '暂时不可用' }, status)
  })
  showApp()
  expect(await screen.findByText('暂时无法验证登录状态')).toBeTruthy()
  expect(screen.queryByText('登录页面')).toBeNull()
  adapter.mockImplementation(async config => httpResponse(config, config.url === '/operations' ? [] : { id: 1, username: 'owner', role: 'OWNER' }))
  fireEvent.click(screen.getByRole('button', { name: '重试' }))
  await waitFor(() => expect(screen.getByText('服务器总览')).toBeTruthy())
})
