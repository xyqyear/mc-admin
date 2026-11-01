import { test, expect, login } from './fixtures'
import { withCleanup } from './cleanup'

test('shared monitoring survives navigation, transport failure and server restart', {
  annotation: { type: 'shard_isolation', description: 'independent' },
}, async ({ page, api, owned }) => {
  await api.running()
  await login(page, owned)
  await page.goto('/overview')
  await expect(page.getByRole('link', { name: '服务器详情', exact: true })).toBeVisible()
  const requests: string[] = []
  page.on('request', request => { if (request.method() === 'GET') requests.push(new URL(request.url()).pathname) })
  await withCleanup(async () => {
    await page.waitForTimeout(4500)
    expect(requests.filter(path => path === '/api/monitoring').length).toBeGreaterThanOrEqual(2)
    expect(requests.filter(path => path === '/api/monitoring').length).toBeLessThanOrEqual(3)
    expect(requests.filter(path => /\/api\/(system\/(info|cpu_percent|disk-usage)|servers\/[^/]+\/(status|maintenance|cpu_percent|memory|iostats|disk-usage))$/.test(path))).toEqual([])
    await page.getByRole('link', { name: '服务器详情', exact: true }).click()
    await expect(page).toHaveURL(new URL(`/server/${owned.server_id}`, owned.base_url).href)
    await expect(page.getByText('系统资源使用情况', { exact: true })).toBeVisible()
    await expect(page.getByRole('button', { name: '停止', exact: true })).toBeEnabled()
    let unavailable = true
    await page.route('**/api/monitoring', route => unavailable
      ? route.fulfill({ status: 503, json: { detail: '浏览器测试：监控连接暂不可用' } })
      : route.continue())
    await expect(page.getByText('（数据已过期）').first()).toBeVisible()
    await expect(page.getByRole('button', { name: '停止', exact: true })).toBeDisabled()
    unavailable = false
    await expect(page.getByRole('button', { name: '停止', exact: true })).toBeEnabled()
    await api.stopped()
    await expect(page.getByText('服务器未运行').first()).toBeVisible()
    await expect(page.getByRole('button', { name: '启动', exact: true })).toBeEnabled()
    await api.running()
    await expect(page.getByRole('button', { name: '停止', exact: true })).toBeEnabled()
    await expect(page.getByText('服务器未运行')).toHaveCount(0)
  },
  { label: 'monitoring transport', run: () => page.unrouteAll({ behavior: 'wait' }) },
  { label: 'running Minecraft', run: () => api.running() })
})
