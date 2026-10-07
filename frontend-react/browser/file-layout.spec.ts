import type { Locator, Page } from '@playwright/test'
import { test, expect, login, type OwnedApi } from './fixtures'
import { withCleanup } from './cleanup'

const isolated = { annotation: { type: 'shard_isolation', description: 'independent' } }
const ignoredReason = '此范围已被快照规则忽略，不能创建快照或恢复'

type TargetCheck = { allowed: boolean; reason?: string }

function heldTarget() {
  let release!: () => void
  let received!: (value: TargetCheck) => void
  let failed!: (reason: unknown) => void
  return {
    release: () => release(),
    held: new Promise<void>(resolve => { release = resolve }),
    ready: new Promise<TargetCheck>((resolve, reject) => { received = resolve; failed = reject }),
    received: (value: TargetCheck) => received(value),
    failed: (reason: unknown) => failed(reason),
  }
}

async function holdTargetChecks(page: Page, paths: string[]) {
  const targets = new Map(paths.map(path => [path, heldTarget()]))
  await page.route('**/api/snapshots/targets/check', async route => {
    const request = route.request()
    const scope = request.method() === 'POST'
      ? (request.postDataJSON() as { scope?: { kind: string; paths?: string[] } }).scope
      : undefined
    const target = scope?.kind === 'paths' && scope.paths?.length === 1
      ? targets.get(scope.paths[0])
      : undefined
    if (!target) { await route.continue(); return }
    try {
      const response = await route.fetch()
      expect(response.status()).toBe(200)
      target.received(await response.json() as TargetCheck)
      await target.held
      await route.fulfill({ response })
    } catch (error) {
      target.failed(error)
      throw error
    }
  })
  return {
    target: (path: string) => targets.get(path)!,
    close: async () => {
      for (const target of targets.values()) target.release()
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
  let checks: Awaited<ReturnType<typeof holdTargetChecks>> | undefined
  await withCleanup(async () => {
    await sourceFiles(api, root, () => { created = true })
    await api.json('/api/config/modules/snapshots', 'PUT', { config_data: { ...config.config_data, ignored_paths: [...(config.config_data.ignored_paths as string[]), root + '/ignored'] } })
    rulesChanged = true
    checks = await holdTargetChecks(page, [root + '/allowed.txt', root + '/ignored'])
    await login(page, owned)
    await page.goto(`/server/${owned.server_id}/files?path=${encodeURIComponent('/' + root)}`)
    const allowed = page.getByRole('checkbox', { name: `选择 /${root}/allowed.txt`, exact: true })
    const ignored = page.getByRole('checkbox', { name: `选择 /${root}/ignored`, exact: true })
    await expect(allowed).toBeVisible()
    await expect(ignored).toBeVisible()
    await page.evaluate(() => document.fonts.ready)
    const toolbar = page.locator('[role="toolbar"][aria-label="所选文件操作"]')
    await expect(toolbar).toBeHidden()
    const measured = [page.getByRole('row').filter({ has: allowed }), page.getByRole('row').filter({ has: ignored }), toolbar]
    const before = await geometry(measured)
    expect(await checks.target(root + '/allowed.txt').ready).toMatchObject({ allowed: true })
    expect(await checks.target(root + '/ignored').ready).toMatchObject({ allowed: false, reason: ignoredReason })

    await allowed.click()
    await expect(allowed).toBeChecked()
    await expect(toolbar).toBeVisible()
    await snapshotFeedback(page, toolbar, '正在检查忽略规则')
    expect(await geometry(measured)).toEqual(before)
    checks.target(root + '/allowed.txt').release()
    await expect(toolbar.getByRole('button', { name: '创建快照', exact: true })).toBeEnabled()
    await expect(toolbar.getByRole('button', { name: '快照恢复', exact: true })).toBeEnabled()
    expect(await geometry(measured)).toEqual(before)
    await allowed.click()
    await expect(allowed).not.toBeChecked()
    await expect(toolbar).toBeHidden()
    expect(await geometry(measured)).toEqual(before)

    await ignored.click()
    await expect(ignored).toBeChecked()
    await snapshotFeedback(page, toolbar, '正在检查忽略规则')
    expect(await geometry(measured)).toEqual(before)
    checks.target(root + '/ignored').release()
    await snapshotFeedback(page, toolbar, ignoredReason)
    expect(await geometry(measured)).toEqual(before)
    await ignored.click()
    await expect(ignored).not.toBeChecked()
    await expect(toolbar).toBeHidden()
    expect(await geometry(measured)).toEqual(before)
    expect((await api.file(root + '/allowed.txt')).content).toBe('allowed layout bytes\n')
    expect((await api.file(root + '/ignored/keep.txt')).content).toBe('protected layout bytes\n')
  },
  { label: 'target-check transport', run: async () => { await checks?.close() } },
  { label: 'snapshot rules', run: async () => { if (rulesChanged) await api.json('/api/config/modules/snapshots', 'PUT', config) } },
  { label: 'file layout source', run: async () => { if (created) await api.deleteFile(root) } },
  )
})

test('advanced search selection and delayed ignore feedback preserve result rows and batch toolbar geometry', isolated, async ({ page, api, owned }) => {
  const root = `browser-search-layout-${Date.now().toString(36)}`
  const config = await api.json<{ config_data: Record<string, unknown> }>('/api/config/modules/snapshots')
  let created = false
  let rulesChanged = false
  let checks: Awaited<ReturnType<typeof holdTargetChecks>> | undefined
  await withCleanup(async () => {
    await sourceFiles(api, root, () => { created = true })
    await api.json('/api/config/modules/snapshots', 'PUT', { config_data: { ...config.config_data, ignored_paths: [...(config.config_data.ignored_paths as string[]), root + '/ignored'] } })
    rulesChanged = true
    checks = await holdTargetChecks(page, [root + '/allowed.txt', root + '/ignored'])
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
    const measured = [allowed.locator('..'), ignored.locator('..'), toolbar]
    const before = await geometry(measured)
    expect(await checks.target(root + '/allowed.txt').ready).toMatchObject({ allowed: true })
    expect(await checks.target(root + '/ignored').ready).toMatchObject({ allowed: false, reason: ignoredReason })

    await allowed.click()
    await expect(allowed).toBeChecked()
    await expect(toolbar).toBeVisible()
    await snapshotFeedback(page, toolbar, '正在检查忽略规则')
    expect(await geometry(measured)).toEqual(before)
    checks.target(root + '/allowed.txt').release()
    await expect(toolbar.getByRole('button', { name: '创建快照', exact: true })).toBeEnabled()
    await expect(toolbar.getByRole('button', { name: '快照恢复', exact: true })).toBeEnabled()
    expect(await geometry(measured)).toEqual(before)
    await search.getByRole('button', { name: '清空选择', exact: true }).click()
    await expect(allowed).not.toBeChecked()
    await expect(toolbar).toBeHidden()
    expect(await geometry(measured)).toEqual(before)

    await ignored.click()
    await expect(ignored).toBeChecked()
    await snapshotFeedback(page, toolbar, '正在检查忽略规则')
    expect(await geometry(measured)).toEqual(before)
    checks.target(root + '/ignored').release()
    await snapshotFeedback(page, toolbar, ignoredReason)
    expect(await geometry(measured)).toEqual(before)
    await search.getByRole('button', { name: '清空选择', exact: true }).click()
    await expect(ignored).not.toBeChecked()
    await expect(toolbar).toBeHidden()
    expect(await geometry(measured)).toEqual(before)
    expect((await api.file(root + '/allowed.txt')).content).toBe('allowed layout bytes\n')
    expect((await api.file(root + '/ignored/keep.txt')).content).toBe('protected layout bytes\n')
  },
  { label: 'target-check transport', run: async () => { await checks?.close() } },
  { label: 'snapshot rules', run: async () => { if (rulesChanged) await api.json('/api/config/modules/snapshots', 'PUT', config) } },
  { label: 'search layout source', run: async () => { if (created) await api.deleteFile(root) } },
  )
})
