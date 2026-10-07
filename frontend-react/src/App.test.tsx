import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { AxiosError } from 'axios'
import type { ReactNode } from 'react'
import { api, AUTH_EXPIRED_EVENT, queryKeys } from '@/shared/http/api'
import { createTestClient, deferred, httpResponse } from '@/test/http'
import { TestProviders } from '@/test/TestProviders'
import App from '@/App'
import { useLogin } from '@/features/users/authCommands'
import { useCurrentUser } from '@/features/users/queries'
import { useServers } from '@/features/servers/queries'
import type { ServerListItem } from '@/features/servers/contracts'

vi.mock('@/app/layout/MainLayout', () => ({ MainLayout: ({ children }: { children: ReactNode }) => <main>{children}</main> }))
vi.mock('@/app/version/VersionUpdateDialog', () => ({ default: () => null }))
vi.mock('@/app/version/useVersionCheck', () => ({ useVersionCheck: () => ({ shouldShowDialog: false }) }))
vi.mock('@/features/users/LoginScreen', () => ({ default: function LoginFixture() {
  const login = useLogin()
  return <div>登录页面<button onClick={() => login.mutate({ username: 'new-owner', password: 'new-password' })}>登录新账号</button></div>
} }))
vi.mock('@/app/overview/Overview', () => ({ default: () => <div>服务器总览</div> }))
vi.mock('@/features/health/SelfCheckScreen', () => ({ default: function SelfCheckFixture() {
  const user = useCurrentUser()
  const servers = useServers()
  return <div>{user.data?.username}：{servers.data?.map(server => server.id).join(',')}</div>
} }))

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
  adapter.mockImplementation(async config => httpResponse(config, config.url === '/operations/changes' ? { items: [], next_cursor: 'app:0', has_more: false, active_count: 0, reset_required: true } : { id: 1, username: 'owner', role: 'OWNER' }))
  fireEvent.click(screen.getByRole('button', { name: '重试' }))
  await waitFor(() => expect(screen.getByText('服务器总览')).toBeTruthy())
})

it.each(['event', 'http401'])('clears the real expired session and isolates the next login from late observation (%s)', async trigger => {
  const oldObservation = deferred<void>()
  let owner: 'old' | 'logged-out' | 'new' = 'old'
  let operationReads = 0
  let oldSignal: AbortSignal | undefined
  let credentials: Record<string, unknown> | undefined
  const serverRecord = (id: string): ServerListItem => ({ id, name: id, serverType: 'vanilla', gameVersion: '1.21.4', gamePort: 25565, maxMemoryBytes: 1024, rconPort: 25575, javaVersion: 21 })
  adapter.mockImplementation(async config => {
    if (config.url === '/user/me') return httpResponse(config,
      owner === 'logged-out' ? { detail: '未登录' } : { id: owner === 'old' ? 1 : 2, username: owner === 'old' ? 'old-owner' : 'new-owner', role: 'owner' },
      owner === 'logged-out' ? 401 : 200)
    if (config.url === '/auth/token') {
      credentials = Object.fromEntries(config.data.entries())
      owner = 'new'
      return httpResponse(config, { user: { id: 2, username: 'new-owner', role: 'owner' } })
    }
    if (config.url === '/servers/') return httpResponse(config, [serverRecord(owner === 'new' ? 'new-server' : 'old-server')])
    if (config.url === '/expired-session') return httpResponse(config, { detail: '登录已过期' }, 401)
    if (config.url === '/operations/changes') {
      operationReads++
      if (operationReads === 2) {
        oldSignal = config.signal
        await oldObservation.promise
        return httpResponse(config, { items: [{ sequence: 1, operation_id: 'late-old', kind: 'server_rebuild', state: 'succeeded', data_changed: true,
          resources: [{ kind: 'server', server_id: 'alpha', generation: 1, path: '' }] }], next_cursor: 'old:1', has_more: false, active_count: 0, reset_required: false })
      }
      return httpResponse(config, { items: [], next_cursor: `${owner}:0`, has_more: false, active_count: 0, reset_required: true })
    }
    throw new Error(`unexpected request: ${config.url}`)
  })
  client.setQueryData(queryKeys.servers(), [serverRecord('old-server')])
  client.setQueryData(queryKeys.compose.detail('alpha'), { yaml_content: 'old-secret' })
  showApp()
  await screen.findByText('服务器总览')
  await waitFor(() => expect(client.getQueryData(queryKeys.operations.session('1'))).toEqual({ cursor: 'old:0', active_count: 0 }))
  const polling = client.refetchQueries({ queryKey: queryKeys.operations.session('1') })
  await waitFor(() => expect(oldSignal).toBeDefined())
  owner = 'logged-out'
  await act(async () => {
    if (trigger === 'event') window.dispatchEvent(new Event(AUTH_EXPIRED_EVENT))
    else await api.get('/expired-session').catch(() => undefined)
  })
  await screen.findByText('登录页面')
  expect(client.getQueryData(queryKeys.user.me())).toBeUndefined()
  expect(client.getQueryData(queryKeys.servers())).toBeUndefined()
  expect(client.getQueryData(queryKeys.compose.detail('alpha'))).toBeUndefined()
  expect(client.getQueryData(queryKeys.operations.session('1'))).toBeUndefined()
  expect(oldSignal?.aborted).toBe(true)
  fireEvent.click(screen.getByRole('button', { name: '登录新账号' }))
  await screen.findByText('new-owner：new-server')
  expect(credentials).toEqual({ grant_type: 'password', username: 'new-owner', password: 'new-password' })
  expect(client.getQueryData(queryKeys.user.me())).toMatchObject({ id: 2, username: 'new-owner' })
  await waitFor(() => expect(client.getQueryData(queryKeys.operations.session('2'))).toEqual({ cursor: 'new:0', active_count: 0 }))
  client.setQueryData(queryKeys.compose.detail('alpha'), { yaml_content: 'new-secret' })
  await act(async () => { oldObservation.resolve(); await polling })
  expect(client.getQueryData(queryKeys.operations.session('1'))).toBeUndefined()
  expect(client.getQueryData(queryKeys.compose.detail('alpha'))).toEqual({ yaml_content: 'new-secret' })
  expect(client.getQueryState(queryKeys.compose.detail('alpha'))?.isInvalidated).toBe(false)
})
