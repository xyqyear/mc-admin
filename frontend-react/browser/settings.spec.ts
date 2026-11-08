import { test, expect, login } from './fixtures'
import { withCleanup } from './cleanup'

test('settings submenu opens dedicated pages and saves world values through the real API', { annotation: { type: 'shard_isolation', description: 'independent' } }, async ({ page, api, owned }, testInfo) => {
  const original = await api.json<Record<string, unknown>>('/api/settings/world')
  await withCleanup(async () => {
    await login(page, owned)
    await page.goto('/settings/world')
    await expect(page.getByRole('heading', { name: '世界设置', exact: true })).toBeVisible()
    for (const name of ['DNS 设置', '快照设置', '日志解析', '玩家设置', '地图渲染', '世界设置', '自检设置']) {
      await expect(page.getByRole('link', { name, exact: true })).toBeVisible()
    }
    await expect(page.getByRole('link', { name: '世界设置', exact: true })).toHaveAttribute('data-active')
    await page.getByLabel('维度扫描最大深度', { exact: true }).fill('0')
    await page.getByLabel('维度名称值 1', { exact: true }).fill('浏览器设置验证')
    const saved = page.waitForResponse(response => response.url().endsWith('/api/settings/world') && response.request().method() === 'PUT')
    await page.getByRole('button', { name: '保存设置', exact: true }).click()
    await page.getByRole('button', { name: '确认提交', exact: true }).click()
    expect((await saved).status()).toBe(200)
    const effective = await api.json<{ dimension_max_depth_from_world_root: number; dimension_labels: Record<string, string> }>('/api/settings/world')
    expect(effective.dimension_max_depth_from_world_root).toBe(0)
    expect(Object.values(effective.dimension_labels)).toContain('浏览器设置验证')
    await page.getByRole('link', { name: '自检设置', exact: true }).click()
    await expect(page.getByRole('checkbox').first()).toBeVisible()
    for (const checkbox of await page.getByRole('checkbox').all()) {
      const box = await checkbox.boundingBox()
      expect(box).not.toBeNull()
      expect(box!.width).toBeCloseTo(box!.height, 1)
      expect(box!.width).toBeLessThanOrEqual(24)
    }
    await page.screenshot({ path: testInfo.outputPath('settings-checkboxes.png') })
    await page.getByRole('link', { name: '日志解析', exact: true }).click()
    await expect(page.getByLabel('玩家加入解析规则', { exact: true })).toHaveJSProperty('tagName', 'TEXTAREA')
    await page.getByRole('link', { name: '玩家设置', exact: true }).click()
    await expect(page.getByRole('group', { name: 'Query 命令模板', exact: true }).locator('.monaco-editor')).toBeVisible()
    await page.getByRole('link', { name: '世界设置', exact: true }).click()
    await expect(page.getByLabel('维度扫描最大深度', { exact: true })).toHaveValue('0')
  }, { label: 'world settings', run: async () => { await api.json('/api/settings/world', 'PUT', original) } })
})

test('template inputs preserve typed zero and false and validate preview values', { annotation: { type: 'shard_isolation', description: 'independent' } }, async ({ page, api, owned }) => {
  const compose = await api.json<{ yaml_content: string }>(api.server('/compose'))
  const template = await api.json<{ id: number }>('/api/templates/', 'POST', {
    name: `browser-values-${owned.run_id}`,
    yaml_template: compose.yaml_content + '\n# typed: {name} {count} {ratio} {mode} {enabled}\n',
    variable_definitions: [
      { type: 'string', name: 'name', display_name: '模板服务器名', default: 'browser-template', pattern: '^[a-z0-9-]+$' },
      { type: 'int', name: 'count', display_name: '计数', default: 0, min_value: 0, max_value: 8 },
      { type: 'float', name: 'ratio', display_name: '比例', default: 1.5, min_value: 0, max_value: 2 },
      { type: 'enum', name: 'mode', display_name: '运行模式', default: 'safe', options: ['safe', 'fast'] },
      { type: 'bool', name: 'enabled', display_name: '启用测试', default: false },
    ],
  }, 201)
  await withCleanup(async () => {
    await login(page, owned)
    await page.goto('/server/new')
    await page.getByRole('combobox').first().click()
    await page.getByRole('option', { name: `browser-values-${owned.run_id}`, exact: true }).click()
    await expect(page.getByLabel('计数', { exact: true })).toHaveValue('0')
    await page.getByLabel('计数', { exact: true }).fill('9')
    await expect(page.getByRole('button', { name: '创建服务器', exact: true })).toBeDisabled()
    await page.getByLabel('计数', { exact: true }).fill('')
    await expect(page.getByRole('button', { name: '创建服务器', exact: true })).toBeDisabled()
    await page.getByLabel('计数', { exact: true }).fill('0')
    await page.getByLabel('比例', { exact: true }).fill('2')
    await page.getByRole('combobox', { name: '运行模式', exact: true }).click()
    await page.getByRole('option', { name: 'fast', exact: true }).click()
    await page.getByRole('checkbox', { name: '启用测试', exact: true }).check()
    await page.getByRole('checkbox', { name: '启用测试', exact: true }).uncheck()
    await expect(page.getByRole('button', { name: '创建服务器', exact: true })).toBeEnabled()
    const preview = page.waitForResponse(response => response.url().endsWith(`/api/templates/${template.id}/preview`))
    await page.getByRole('button', { name: '预览 YAML', exact: true }).click()
    const response = await preview
    expect(response.status()).toBe(200)
    expect(response.request().postDataJSON()).toEqual({ variable_values: { name: 'browser-template', count: 0, ratio: 2, mode: 'fast', enabled: false } })
    expect((await response.json()).rendered_yaml).toContain('# typed: browser-template 0 2 fast False')
    await expect(page.getByRole('dialog', { name: '预览生成的 YAML' })).toBeVisible()
  }, { label: 'typed template', run: async () => { expect((await api.response(`/api/templates/${template.id}`, 'DELETE')).status).toBe(204) } })
})

test('Enter in a scheduled job parameter waits for explicit save', { annotation: { type: 'shard_isolation', description: 'independent' } }, async ({ page, api, owned }) => {
  const name = `browser-plan-${owned.run_id}`
  let id: string | undefined
  await withCleanup(async () => {
    await login(page, owned)
    await page.goto('/cron')
    await page.getByRole('button', { name: '创建任务', exact: true }).click()
    const dialog = page.getByRole('dialog')
    await dialog.getByRole('combobox').first().click()
    await page.getByRole('option', { name: '重启服务器', exact: true }).click()
    await dialog.getByLabel('任务名称', { exact: true }).fill(name)
    await dialog.getByLabel('服务器 ID', { exact: true }).fill(owned.server_id)
    await dialog.getByLabel('服务器 ID', { exact: true }).press('Enter')
    await expect(dialog).toBeVisible()
    expect((await api.json<{ name: string }[]>('/api/cron/')).some(job => job.name === name)).toBe(false)
    const saved = page.waitForResponse(response => response.url().endsWith('/api/cron/') && response.request().method() === 'POST')
    await dialog.getByRole('button', { name: '创建任务', exact: true }).click()
    const response = await saved
    expect(response.status()).toBe(200)
    id = (await response.json()).cronjob_id
    expect((await api.json<{ name: string; params: { server_id: string } }>(`/api/cron/${id}`))).toMatchObject({ name, params: { server_id: owned.server_id } })
  }, { label: 'scheduled job', run: async () => {
    if (!id) id = (await api.json<{ name: string; cronjob_id: string }[]>('/api/cron/')).find(job => job.name === name)?.cronjob_id
    if (id) await api.json(`/api/cron/${id}`, 'DELETE')
  } })
})
