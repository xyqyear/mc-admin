import type { Locator, Page, Request } from '@playwright/test'
import { test, expect, login, type OwnedApi } from './fixtures'
import { withCleanup } from './cleanup'

const isolated = { annotation: { type: 'shard_isolation', description: 'independent' } }
const ignoredReason = '此范围已被快照规则忽略，不能创建快照或恢复'

type TargetRules = { ignored_paths: string[] }

function heldTarget() {
  let release!: () => void
  let received!: (value: TargetRules) => void
  let failed!: (reason: unknown) => void
  return {
    release: () => release(),
    held: new Promise<void>(resolve => { release = resolve }),
    ready: new Promise<TargetRules>((resolve, reject) => { received = resolve; failed = reject }),
    received: (value: TargetRules) => received(value),
    failed: (reason: unknown) => failed(reason),
  }
}

async function holdTargetRules(page: Page) {
  const target = heldTarget()
  let reads = 0
  let posts = 0
  const observe = (request: Request) => {
    if (new URL(request.url()).pathname === '/api/snapshots/targets/check' && request.method() === 'POST') posts++
  }
  page.on('request', observe)
  await page.route('**/api/snapshots/targets/rules?*', async route => {
    reads++
    try {
      const response = await route.fetch()
      expect(response.status()).toBe(200)
      target.received(await response.json() as TargetRules)
      await target.held
      await route.fulfill({ response })
    } catch (error) {
      target.failed(error)
      throw error
    }
  })
  return {
    ready: target.ready,
    release: target.release,
    reads: () => reads,
    posts: () => posts,
    close: async () => {
      target.release()
      page.off('request', observe)
      await page.unrouteAll({ behavior: 'wait' })
    },
  }
}

async function sourceFiles(api: OwnedApi, root: string, onCreated: () => void) {
  await api.json(api.server('/files/create'), 'POST', { path: '/', name: root, type: 'directory' })
  onCreated()
  await api.json(api.server('/files/create'), 'POST', { path: '/' + root, name: 'allowed.txt', type: 'file' })
  await api.writeFile(root + '/allowed.txt', 'allowed layout bytes\n')
  await api.json(api.server('/files/create'), 'POST', { path: '/' + root, name: 'ignored', type: 'directory' })
  await api.json(api.server('/files/create'), 'POST', { path: '/' + root + '/ignored', name: 'keep.txt', type: 'file' })
  await api.writeFile(root + '/ignored/keep.txt', 'protected layout bytes\n')
}

async function geometry(locators: Locator[]) {
  return Promise.all(locators.map(locator => locator.evaluate(element => {
    const rect = element.getBoundingClientRect()
    return { x: rect.x, y: rect.y, width: rect.width, height: rect.height }
  })))
}

async function snapshotFeedback(page: Page, toolbar: Locator, reason: string) {
  const creation = toolbar.getByRole('button', { name: '创建快照', exact: true })
  await expect(creation).toBeDisabled()
  await expect(toolbar.getByRole('button', { name: '快照恢复', exact: true })).toBeDisabled()
  await expect(toolbar.getByRole('button', { name: '下载到文件夹', exact: true })).toBeEnabled()
  await expect(toolbar.getByRole('button', { name: '打包所选', exact: true })).toBeEnabled()
  await expect(toolbar.getByText(reason, { exact: true })).toHaveCount(0)
  await creation.locator('..').hover()
  await expect(page.locator('[data-slot="tooltip-content"]:visible')).toHaveText(reason)
  await page.mouse.move(0, 0)
  await expect(page.locator('[data-slot="tooltip-content"]:visible')).toHaveCount(0)
}

test('file selection and delayed ignore feedback preserve table rows and batch toolbar geometry', isolated, async ({ page, api, owned }) => {
  const root = `browser-file-layout-${Date.now().toString(36)}`
  const config = await api.json<{ config_data: Record<string, unknown> }>('/api/config/modules/snapshots')
  let created = false
  let rulesChanged = false
  let checks: Awaited<ReturnType<typeof holdTargetRules>> | undefined
  await withCleanup(async () => {
    await sourceFiles(api, root, () => { created = true })
    await api.json('/api/config/modules/snapshots', 'PUT', { config_data: { ...config.config_data, ignored_paths: [...(config.config_data.ignored_paths as string[]), root + '/ignored'] } })
    rulesChanged = true
    checks = await holdTargetRules(page)
    await login(page, owned)
    await page.goto(`/server/${owned.server_id}/files?path=${encodeURIComponent('/' + root)}`)
    const allowed = page.getByRole('checkbox', { name: `选择 /${root}/allowed.txt`, exact: true })
    const ignored = page.getByRole('checkbox', { name: `选择 /${root}/ignored`, exact: true })
    await expect(allowed).toBeVisible()
    await expect(ignored).toBeVisible()
    await page.evaluate(() => document.fonts.ready)
    const toolbar = page.locator('[role="toolbar"][aria-label="所选文件操作"]')
    await expect(toolbar).toBeHidden()
    const rows = [page.getByRole('row').filter({ has: allowed }), page.getByRole('row').filter({ has: ignored })]
    const measured = [...rows, toolbar]
    const before = await geometry(rows)
    expect((await checks.ready).ignored_paths).toContain(root + '/ignored')

    await allowed.click()
    await expect(allowed).toBeChecked()
    await expect(toolbar).toBeVisible()
    await snapshotFeedback(page, toolbar, '正在检查忽略规则')
    expect(await geometry(rows)).toEqual(before)
    const selectedGeometry = await geometry(measured)
    checks.release()
    await expect(toolbar.getByRole('button', { name: '创建快照', exact: true })).toBeEnabled()
    await expect(toolbar.getByRole('button', { name: '快照恢复', exact: true })).toBeEnabled()
    expect(await geometry(measured)).toEqual(selectedGeometry)
    await allowed.click()
    await expect(allowed).not.toBeChecked()
    await expect(toolbar).toBeHidden()
    expect(await geometry(rows)).toEqual(before)

    await ignored.click()
    await expect(ignored).toBeChecked()
    await snapshotFeedback(page, toolbar, ignoredReason)
    expect(await geometry(measured)).toEqual(selectedGeometry)
    await ignored.click()
    await expect(ignored).not.toBeChecked()
    await expect(toolbar).toBeHidden()
    expect(await geometry(rows)).toEqual(before)
    expect(checks.reads()).toBe(1)
    expect(checks.posts()).toBe(0)
    expect((await api.file(root + '/allowed.txt')).content).toBe('allowed layout bytes\n')
    expect((await api.file(root + '/ignored/keep.txt')).content).toBe('protected layout bytes\n')
    await page.getByRole('button', { name: '系统自检', exact: true }).click()
    await expect(page).toHaveURL('/')
    await api.json('/api/config/modules/snapshots', 'PUT', { config_data: { ...config.config_data, ignored_paths: [...(config.config_data.ignored_paths as string[]), root + '/allowed.txt'] } })
    await page.goBack()
    await expect(page.getByRole('button', { name: '为 allowed.txt 创建快照', exact: true })).toBeDisabled()
    await expect(page.getByRole('button', { name: '为 ignored 创建快照', exact: true })).toBeEnabled()
    expect(checks.reads()).toBe(2)
    expect(checks.posts()).toBe(0)
  },
  { label: 'target-rule transport', run: async () => { await checks?.close() } },
  { label: 'snapshot rules', run: async () => { if (rulesChanged) await api.json('/api/config/modules/snapshots', 'PUT', config) } },
  { label: 'file layout source', run: async () => { if (created) await api.deleteFile(root) } },
  )
})

test('advanced search selection and delayed ignore feedback preserve result rows and batch toolbar geometry', isolated, async ({ page, api, owned }) => {
  const root = `browser-search-layout-${Date.now().toString(36)}`
  const config = await api.json<{ config_data: Record<string, unknown> }>('/api/config/modules/snapshots')
  let created = false
  let rulesChanged = false
  let checks: Awaited<ReturnType<typeof holdTargetRules>> | undefined
  await withCleanup(async () => {
    await sourceFiles(api, root, () => { created = true })
    await api.json('/api/config/modules/snapshots', 'PUT', { config_data: { ...config.config_data, ignored_paths: [...(config.config_data.ignored_paths as string[]), root + '/ignored'] } })
    rulesChanged = true
    checks = await holdTargetRules(page)
    await login(page, owned)
    await page.goto(`/server/${owned.server_id}/files?path=${encodeURIComponent('/' + root)}`)
    await page.getByRole('button', { name: '高级搜索', exact: true }).click()
    const search = page.getByRole('dialog', { name: '高级搜索' })
    await search.getByLabel('搜索模式', { exact: true }).fill('^(allowed[.]txt|ignored)$')
    await search.getByRole('button', { name: '搜索', exact: true }).click()
    const allowed = search.getByRole('checkbox', { name: '选择搜索结果 /allowed.txt', exact: true })
    const ignored = search.getByRole('checkbox', { name: '选择搜索结果 /ignored', exact: true })
    await expect(allowed).toBeVisible()
    await expect(ignored).toBeVisible()
    await page.evaluate(() => document.fonts.ready)
    const toolbar = search.locator('[role="toolbar"][aria-label="所选文件操作"]')
    await expect(toolbar).toBeHidden()
    const rows = [allowed.locator('..'), ignored.locator('..')]
    const measured = [...rows, toolbar]
    const before = await geometry(rows)
    expect((await checks.ready).ignored_paths).toContain(root + '/ignored')

    await allowed.click()
    await expect(allowed).toBeChecked()
    await expect(toolbar).toBeVisible()
    await snapshotFeedback(page, toolbar, '正在检查忽略规则')
    expect(await geometry(rows)).toEqual(before)
    const selectedGeometry = await geometry(measured)
    checks.release()
    await expect(toolbar.getByRole('button', { name: '创建快照', exact: true })).toBeEnabled()
    await expect(toolbar.getByRole('button', { name: '快照恢复', exact: true })).toBeEnabled()
    expect(await geometry(measured)).toEqual(selectedGeometry)
    await search.getByRole('button', { name: '清空选择', exact: true }).click()
    await expect(allowed).not.toBeChecked()
    await expect(toolbar).toBeHidden()
    expect(await geometry(rows)).toEqual(before)

    await ignored.click()
    await expect(ignored).toBeChecked()
    await snapshotFeedback(page, toolbar, ignoredReason)
    expect(await geometry(measured)).toEqual(selectedGeometry)
    expect(checks.reads()).toBe(1)
    expect(checks.posts()).toBe(0)
    await search.getByRole('button', { name: '清空选择', exact: true }).click()
    await expect(ignored).not.toBeChecked()
    await expect(toolbar).toBeHidden()
    expect(await geometry(rows)).toEqual(before)
    expect((await api.file(root + '/allowed.txt')).content).toBe('allowed layout bytes\n')
    expect((await api.file(root + '/ignored/keep.txt')).content).toBe('protected layout bytes\n')
  },
  { label: 'target-rule transport', run: async () => { await checks?.close() } },
  { label: 'snapshot rules', run: async () => { if (rulesChanged) await api.json('/api/config/modules/snapshots', 'PUT', config) } },
  { label: 'search layout source', run: async () => { if (created) await api.deleteFile(root) } },
  )
})
