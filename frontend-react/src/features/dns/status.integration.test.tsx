import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterAll, afterEach, beforeAll, beforeEach, expect, it, vi } from 'vitest'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { toast } from 'sonner'
import DnsManagementScreen from '@/features/dns/DnsManagementScreen'
import type { DNSStatusResponse } from '@/features/dns/contracts'
import { createTestClient } from '@/test/http'
import { TestProviders } from '@/test/TestProviders'

const server = setupServer()
beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
afterAll(() => server.close())
let client: ReturnType<typeof createTestClient>
let status: DNSStatusResponse
let routes: Record<string, string>
let updates = 0
const noDnsChanges = { records_to_add: [], records_to_remove: [], records_to_update: [] }
const noRouteChanges = { routes_to_add: {}, routes_to_remove: {}, routes_to_update: {} }
beforeEach(() => {
  client = createTestClient(); updates = 0; routes = {}
  status = { initialized: true, dns_diff: null, router_diff: noRouteChanges, state: 'degraded', dns_known: false, router_known: true, unknown_servers: ['alpha'], issues: ['DNS记录读取失败，暂缓删除未知配置'] }
  server.use(
    http.get('*/api/dns/enabled', () => HttpResponse.json({ enabled: true })),
    http.get('*/api/dns/status', () => HttpResponse.json(status)),
    http.get('*/api/dns/records', () => HttpResponse.json([])),
    http.get('*/api/dns/routes', () => HttpResponse.json(routes)),
    http.post('*/api/dns/update', () => { updates++; routes = { 'alpha.example.test': 'alpha:25565' }; return HttpResponse.json({ detail: '部分同步失败，请检查DNS提供商后重试' }, { status: 500 }) }),
  )
})
afterEach(() => { client.clear(); server.resetHandlers(); vi.restoreAllMocks() })

it('shows unknown state and preserves updates; a partial failure still refreshes changed routes', async () => {
  const error = vi.spyOn(toast, 'error')
  render(<TestProviders client={client}><DnsManagementScreen /></TestProviders>)
  await screen.findByText('同步状态不完整')
  await screen.findByText('DNS记录读取失败，暂缓删除未知配置')
  expect(screen.queryByText('状态正常')).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: '更新记录' }))
  await waitFor(() => expect(error).toHaveBeenCalledWith('DNS更新失败: 部分同步失败，请检查DNS提供商后重试'))
  await screen.findByText('alpha:25565')
  expect(updates).toBe(1)
  status = { initialized: true, dns_diff: noDnsChanges, router_diff: noRouteChanges, state: 'ready', dns_known: true, router_known: true, issues: [], unknown_servers: [] }
  fireEvent.click(screen.getByTitle('重新获取DNS记录和路由信息'))
  await screen.findByText('状态正常')
})

it('reports failed refresh instead of a success toast', async () => {
  const error = vi.spyOn(toast, 'error'); const success = vi.spyOn(toast, 'success')
  render(<TestProviders client={client}><DnsManagementScreen /></TestProviders>)
  await screen.findByText('同步状态不完整')
  server.use(http.get('*/api/dns/records', () => HttpResponse.json({ detail: '没有读取权限' }, { status: 403 })))
  fireEvent.click(screen.getByTitle('重新获取DNS记录和路由信息'))
  await waitFor(() => expect(error).toHaveBeenCalledWith('刷新失败: 没有读取权限'))
  expect(success).not.toHaveBeenCalledWith('DNS数据已刷新')
})

it.each(['empty', 'legacy-null'] as const)('does not call %s an in-sync state', async mode => {
  status = mode === 'empty'
    ? { initialized: true, dns_diff: null, router_diff: null, state: 'empty', empty_desired: true, issues: ['没有可发布的服务器配置，保留现有记录'] }
    : { initialized: true, dns_diff: null, router_diff: null }
  render(<TestProviders client={client}><DnsManagementScreen /></TestProviders>)
  await screen.findByText(mode === 'empty' ? '无可发布配置，保留现有记录' : '同步状态尚未确认')
  expect(screen.queryByText('状态正常')).toBeNull()
})
