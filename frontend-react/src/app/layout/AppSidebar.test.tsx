import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterAll, afterEach, beforeAll, beforeEach, expect, it, vi } from 'vitest'
import { useLocation } from 'react-router'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { UserRole } from '@/features/users/contracts'
import { queryKeys } from '@/shared/http/api'
import { ThemeProvider } from '@/shared/theme-provider'
import { SidebarProvider, useSidebar } from '@/shared/ui/sidebar'
import { TooltipProvider } from '@/shared/ui/tooltip'
import { createTestClient } from '@/test/http'
import { TestProviders } from '@/test/TestProviders'
import AppSidebar from './AppSidebar'
import { useSidebarStore } from './sidebarStore'

const server = setupServer()
let client: ReturnType<typeof createTestClient>
let role: UserRole
let logouts: number

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterAll(() => server.close())
beforeEach(() => {
  client = createTestClient()
  role = UserRole.OWNER
  logouts = 0
  localStorage.clear()
  useSidebarStore.setState({ openKeys: ['服务器管理'], lastPath: null, collapsed: false })
  vi.stubGlobal('matchMedia', (media: string) => ({
    media, matches: false, onchange: null,
    addListener: vi.fn(), removeListener: vi.fn(),
    addEventListener: vi.fn(), removeEventListener: vi.fn(), dispatchEvent: vi.fn(),
  }))
  server.use(
    http.get('*/api/servers/', () => HttpResponse.json([{ id: 'alpha' }])),
    http.get('*/api/servers/alpha/status', () => HttpResponse.json({ status: 'CREATED' })),
    http.get('*/api/user/me', () => HttpResponse.json({ id: 1, username: 'owner', role })),
    http.get('*/api/self-check/status', () => HttpResponse.json({ current_state: { findings: [] } })),
    http.post('*/api/auth/logout', () => { logouts++; return new HttpResponse(null, { status: 204 }) }),
  )
})
afterEach(() => {
  cleanup()
  client.clear()
  server.resetHandlers()
  useSidebarStore.setState({ openKeys: ['服务器管理'], lastPath: null, collapsed: false })
  localStorage.clear()
  document.documentElement.classList.remove('dark', 'light')
  vi.unstubAllGlobals()
})

function SidebarPage() {
  const location = useLocation()
  const { state } = useSidebar()
  return <>
    <output aria-label="当前路由">{location.pathname}</output>
    <output aria-label="侧边栏状态">{state}</output>
    {location.pathname === '/login' ? <p>登录页</p> : <AppSidebar />}
  </>
}

function renderSidebar() {
  render(<TestProviders client={client} route="/server/alpha/files">
    <ThemeProvider defaultTheme="light">
      <TooltipProvider>
        <SidebarProvider><SidebarPage /></SidebarProvider>
      </TooltipProvider>
    </ThemeProvider>
  </TestProviders>)
}

it('exposes every navigation destination as a link and preserves exact active matching', async () => {
  renderSidebar()
  await screen.findByRole('link', { name: '文件' })
  fireEvent.click(await screen.findByRole('button', { name: '超管' }))
  await screen.findByRole('link', { name: '用户管理' })

  const destinations = [
    ['系统自检', '/'], ['服务器总览', '/overview'], ['服务器模板', '/templates'],
    ['玩家管理', '/players'], ['快照管理', '/snapshots'], ['压缩包管理', '/archives'],
    ['动态配置', '/config'], ['DNS管理', '/dns'], ['任务管理', '/cron'],
    ['概览', '/server/alpha'], ['设置', '/server/alpha/compose'],
    ['文件', '/server/alpha/files'], ['控制台', '/server/alpha/console'],
    ['地图回档', '/server/alpha/world-restore'], ['区块清理', '/server/alpha/chunk-prune'],
    ['新建', '/server/new'], ['用户管理', '/admin/users'],
  ]
  for (const [name, path] of destinations) {
    const link = screen.getByRole('link', { name })
    expect(link.tagName).toBe('A')
    expect(link.getAttribute('href')).toBe(path)
  }
  expect(screen.getAllByRole('link')).toHaveLength(destinations.length)
  expect(screen.getByRole('link', { name: '文件' }).hasAttribute('data-active')).toBe(true)
  expect(screen.getByRole('link', { name: '概览' }).hasAttribute('data-active')).toBe(false)

  fireEvent.click(screen.getByRole('link', { name: '设置' }))
  await waitFor(() => expect(screen.getByLabelText('当前路由').textContent).toBe('/server/alpha/compose'))
  expect(screen.getByRole('link', { name: '设置' }).hasAttribute('data-active')).toBe(true)
  expect(screen.getByRole('link', { name: '文件' }).hasAttribute('data-active')).toBe(false)
  expect(screen.getByRole('link', { name: '概览' }).hasAttribute('data-active')).toBe(false)
  expect(useSidebarStore.getState().openKeys).toEqual(['服务器管理', 'alpha'])
})

it('leaves middle and modified navigation to the browser without changing the source route or menu', async () => {
  renderSidebar()
  await screen.findByRole('link', { name: '文件' })
  const openKeys = [...useSidebarStore.getState().openKeys]
  for (const name of ['服务器总览', '控制台']) {
    const link = screen.getByRole('link', { name })
    for (const [type, options] of [
      ['auxclick', { button: 1 }],
      ['click', { button: 0, ctrlKey: true }],
      ['click', { button: 0, metaKey: true }],
      ['click', { button: 0, shiftKey: true }],
    ] as const) {
      let preventedByApplication: boolean | undefined
      // JSDOM cannot perform the browser's native new-tab navigation.
      document.addEventListener(type, event => {
        preventedByApplication = event.defaultPrevented
        event.preventDefault()
      }, { once: true })
      fireEvent(link, new MouseEvent(type, { bubbles: true, cancelable: true, ...options }))
      expect(preventedByApplication).toBe(false)
      expect(screen.getByLabelText('当前路由').textContent).toBe('/server/alpha/files')
      expect(useSidebarStore.getState().openKeys).toEqual(openKeys)
    }
  }
})

it('keeps role restrictions and group, theme, collapse and logout operations as buttons', async () => {
  role = UserRole.ADMIN
  renderSidebar()
  const serverButton = await screen.findByRole('button', { name: 'alpha' })
  await waitFor(() => expect(client.getQueryData<{ role: UserRole }>(queryKeys.user.me())?.role).toBe(UserRole.ADMIN))
  expect(screen.queryByRole('button', { name: '超管' })).toBeNull()
  expect(screen.queryByRole('link', { name: '用户管理' })).toBeNull()
  expect(serverButton.getAttribute('href')).toBeNull()

  fireEvent.click(serverButton)
  await waitFor(() => expect(screen.queryByRole('link', { name: '文件' })).toBeNull())
  expect(screen.getByLabelText('当前路由').textContent).toBe('/server/alpha/files')
  expect(useSidebarStore.getState().openKeys).toEqual(['服务器管理'])
  fireEvent.click(serverButton)
  await screen.findByRole('link', { name: '文件' })
  fireEvent.click(screen.getByRole('button', { name: '服务器管理' }))
  expect(useSidebarStore.getState().openKeys).toEqual(['alpha'])
  fireEvent.click(screen.getByRole('button', { name: '服务器管理' }))
  await screen.findByRole('link', { name: '文件' })

  fireEvent.click(screen.getByRole('button', { name: '切换主题' }))
  expect(document.documentElement.classList.contains('dark')).toBe(true)
  fireEvent.click(screen.getByRole('button', { name: '收起' }))
  expect(screen.getByLabelText('侧边栏状态').textContent).toBe('collapsed')
  expect(screen.getByLabelText('当前路由').textContent).toBe('/server/alpha/files')

  fireEvent.click(screen.getByRole('button', { name: '退出登录' }))
  await screen.findByText('登录页')
  expect(logouts).toBe(1)
  expect(screen.getByLabelText('当前路由').textContent).toBe('/login')
  expect(client.getQueryCache().getAll()).toHaveLength(0)
})
