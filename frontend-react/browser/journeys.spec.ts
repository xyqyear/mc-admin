import { createHash } from 'node:crypto'
import { readFile, readdir, writeFile } from 'node:fs/promises'
import path from 'node:path'
import type { BrowserContext, Page, WebSocketRoute } from '@playwright/test'
import { test, expect, login, editorValue, navigate, type OwnedApi, type OwnedEnvironment } from './fixtures'
import { interruptRestoreAfterSafetySnapshot } from './streamFault'
import { withCleanup } from './cleanup'

test.describe('owned administration journeys', () => {
  const journeys: Array<{ name: string; run: (fixtures: { page: Page; context: BrowserContext; api: OwnedApi; owned: OwnedEnvironment }) => Promise<void> }> = []
  const journey = (name: string, run: (typeof journeys)[number]['run']) => { journeys.push({ name, run }) }
  test.beforeEach(async ({ page, owned }) => { await login(page, owned) })

  journey('file loading and save failures retain the draft, retry writes exact and deliberately empty bytes', async ({ page, api, owned }) => {
    const filename = 'browser-edit.txt'
    const original = 'loaded-from-real-file\n'
    const draft = 'browser-authored-draft\n'
    await api.json(api.server('/files/create'), 'POST', { path: '/', name: filename, type: 'file' })
    await api.writeFile(filename, original)
    let failRead = true
    let failWrite = true
    await page.route('**/api/servers/*/files/content?*', async route => {
      if (new URL(route.request().url()).searchParams.get('path')?.replace(/^\//, '') === filename && ((route.request().method() === 'GET' && failRead) || (route.request().method() === 'POST' && failWrite))) {
        await route.fulfill({ status: 503, json: { detail: '浏览器测试：连接暂时不可用' } })
      } else await route.continue()
    })
    try {
      await page.goto(`/server/${owned.server_id}/files`)
      await page.getByText(filename, { exact: true }).click()
      const dialog = page.getByRole('dialog', { name: `编辑文件: ${filename}` })
      await expect(dialog.getByText('读取文件失败', { exact: true })).toBeVisible()
      await expect(dialog.getByRole('button', { name: '保存', exact: true })).toBeDisabled()
      failRead = false
      await dialog.getByRole('button', { name: '重试读取' }).click()
      await expect(dialog.getByRole('button', { name: '保存', exact: true })).toBeEnabled()
      await editorValue(page, draft)
      await dialog.getByRole('button', { name: '保存', exact: true }).click()
      await expect(page.getByText(/连接暂时不可用/).first()).toBeVisible()
      await expect(dialog.locator('.view-lines')).toContainText('browser-authored-draft')
      expect((await api.file(filename)).content).toBe(original)
      expect(await readFile(path.join(owned.server_path, 'data', filename), 'utf8')).toBe(original)
      failWrite = false
      await dialog.getByRole('button', { name: '保存', exact: true }).click()
      await expect(dialog).toBeHidden()
      expect((await api.file(filename)).content).toBe(draft)
      expect(await readFile(path.join(owned.server_path, 'data', filename), 'utf8')).toBe(draft)
      await page.getByText(filename, { exact: true }).click()
      await expect(dialog.getByRole('button', { name: '保存', exact: true })).toBeEnabled()
      await editorValue(page, '')
      await dialog.getByRole('button', { name: '保存', exact: true }).click()
      await expect(dialog).toBeHidden()
      expect((await api.file(filename)).content).toBe('')
      expect((await readFile(path.join(owned.server_path, 'data', filename))).length).toBe(0)
    } finally {
      await page.unrouteAll({ behavior: 'wait' })
      await api.json(api.server(`/files?path=${filename}`), 'DELETE')
    }
  })

  journey('Compose rejects a stale confirmed version, compares the draft, and completes after leaving the page', async ({ page, api, owned }) => {
    await api.running()
    const original = await api.json<{ yaml_content: string; version: string }>(api.server('/compose'))
    const draft = '# browser-local-draft\n' + original.yaml_content
    let holdReads = false
    let releaseReads!: () => void
    const readsReleased = new Promise<void>(resolve => { releaseReads = resolve })
    let submittedTaskId: string | undefined
    await page.route('**/api/servers/*/compose', async route => {
      if (route.request().method() === 'GET' && holdReads) await readsReleased
      await route.continue()
    })
    try {
      await page.goto(`/server/${owned.server_id}/files`)
      await navigate(page, `/server/${owned.server_id}/compose`)
      await expect(page.getByRole('button', { name: '提交并重建', exact: true })).toBeEnabled()
      await page.locator('.monaco-editor').first().locator('.view-lines').click({ position: { x: 20, y: 10 } })
      await page.keyboard.press('ControlOrMeta+Home')
      await page.keyboard.insertText('# browser-local-draft')
      await page.keyboard.press('Enter')
      await page.keyboard.press('ControlOrMeta+Home')
      await page.getByRole('button', { name: '提交并重建', exact: true }).click()
      const confirmation = page.getByRole('dialog', { name: '提交并重建服务器' })
      await expect(confirmation).toBeVisible()
      holdReads = true
      await writeFile(path.join(owned.server_path, 'docker-compose.yml'), '# browser-remote-edit\n' + original.yaml_content)
      const conflict = page.waitForResponse(response => response.request().method() === 'POST' && response.url().endsWith('/compose'))
      await confirmation.getByRole('button', { name: '确认重建' }).click()
      const rejected = await conflict
      expect(rejected.status()).toBe(409)
      expect((await rejected.json()).detail.code).toBe('configuration_conflict')
      holdReads = false
      releaseReads()
      await expect(page.getByText('在线配置已变更', { exact: true })).toBeVisible()
      await expect(page.locator('.monaco-editor').first().locator('.view-lines')).toContainText('browser-local-draft')
      expect((await api.json<{ yaml_content: string }>(api.server('/compose'))).yaml_content).toContain('browser-remote-edit')
      await page.getByRole('button', { name: '比较并解决冲突' }).click()
      const comparison = page.getByRole('dialog', { name: '比较配置并确认提交基准' })
      await expect(comparison).toBeVisible()
      await expect(comparison.locator('.monaco-diff-editor')).toHaveCount(2)
      await expect(comparison.getByText('编辑起点', { exact: true })).toBeVisible()
      await expect(comparison.getByText('本地草稿', { exact: true })).toBeVisible()
      await expect(comparison.locator('.view-lines').filter({ hasText: 'browser-remote-edit' }).first()).toBeVisible()
      await expect(comparison.locator('.view-lines').filter({ hasText: 'browser-local-draft' }).first()).toBeVisible()
      await comparison.getByRole('button', { name: '接受此版本为新基准' }).click()
      await page.getByRole('button', { name: '提交并重建', exact: true }).click()
      const accepted = page.waitForResponse(response => response.request().method() === 'POST' && response.url().endsWith('/compose'))
      await page.getByRole('button', { name: '确认重建', exact: true }).click()
      const response = await accepted
      expect(response.status()).toBe(200)
      const { task_id } = await response.json()
      submittedTaskId = task_id
      expect((await api.json<{ status: string }>(`/api/tasks/${task_id}`)).status).toMatch(/^(pending|running)$/)
      await page.goBack()
      await expect(page).toHaveURL(new RegExp(`/server/${owned.server_id}/files$`))
      await api.task(task_id)
      await navigate(page, `/server/${owned.server_id}/compose`)
      await expect(page.locator('.monaco-editor').first().locator('.view-lines')).toContainText('browser-local-draft')
      await expect(page.getByText('在线配置已变更', { exact: true })).toBeHidden()
      expect((await api.json<{ yaml_content: string }>(api.server('/compose'))).yaml_content).toBe(draft)
      expect(await readFile(path.join(owned.server_path, 'docker-compose.yml'), 'utf8')).toBe(draft)
    } finally {
      holdReads = false
      releaseReads()
      await page.unrouteAll({ behavior: 'wait' })
      if (submittedTaskId) await api.task(submittedTaskId, false)
      await writeFile(path.join(owned.server_path, 'docker-compose.yml'), original.yaml_content)
    }
  })

  journey('session lookup retries without discarding authentication, and console reconnect forwards actual commands', async ({ page, context, api, owned }) => {
    await api.running()
    let unavailable = true
    await page.route('**/api/user/me', route => unavailable ? route.fulfill({ status: 503, json: { detail: '浏览器测试：会话查询暂不可用' } }) : route.continue())
    await page.goto('/overview')
    await expect(page.getByText('暂时无法验证登录状态')).toBeVisible()
    await expect(page).toHaveURL(/\/overview$/)
    unavailable = false
    await page.getByRole('button', { name: '重试', exact: true }).click()
    await expect(page.getByRole('button', { name: '退出登录' })).toBeVisible()
    await page.unrouteAll({ behavior: 'wait' })
    await page.getByRole('button', { name: '退出登录' }).click()
    await expect(page).toHaveURL(/\/login$/)
    expect((await context.cookies()).some(cookie => cookie.name === 'mc_admin_session')).toBe(false)
    expect((await context.request.get('/api/user/me')).status()).toBe(401)
    await login(page, owned)
    const status = await api.json<{ status: string }>(api.server('/status'))
    expect(status.status.toLowerCase()).toMatch(/^(healthy|running)$/)
    const sockets: Array<{ page: WebSocketRoute; server: WebSocketRoute }> = []
    const messages: string[] = []
    await page.routeWebSocket('**/api/servers/*/console?*', socket => {
      const server = socket.connectToServer()
      sockets.push({ page: socket, server })
      server.onMessage(message => { messages.push(String(message)); socket.send(message) })
    })
    await page.goto(`/server/${owned.server_id}/console`)
    await expect(page.getByText('已连接', { exact: true })).toBeVisible()
    await expect.poll(() => sockets.length).toBe(1)
    await sockets[0]!.page.close({ code: 1011, reason: 'owned browser connection interruption' })
    await sockets[0]!.server.close()
    await expect.poll(() => sockets.length, { timeout: 15_000 }).toBeGreaterThan(1)
    await expect(page.getByText('已连接', { exact: true })).toBeVisible()
    const marker = 'browser-console-reconnected-' + owned.environment_id
    await page.locator('.xterm-helper-textarea').focus()
    await page.keyboard.type(`say ${marker}`)
    await page.keyboard.press('Enter')
    await expect.poll(() => messages.some(message => message.includes(marker))).toBe(true)
    await expect.poll(async () => (await readFile(path.join(owned.server_path, 'data/logs/latest.log'), 'utf8')).includes(marker)).toBe(true)
    const connections = sockets.length
    await page.getByRole('button', { name: '退出登录' }).click()
    await expect(page).toHaveURL(/\/login$/)
    await page.waitForTimeout(1500)
    expect(sockets).toHaveLength(connections)
  })

  journey('a real restore connection interrupted after its safety snapshot stays visible and can roll back', async ({ page, api, owned }) => {
    await api.stopped()
    await api.initializeMap()
    const marker = 'world/browser-recovery.txt'
    await api.json(api.server('/files/create'), 'POST', { path: '/world', name: 'browser-recovery.txt', type: 'file' })
    await api.writeFile(marker, 'snapshot-state\n')
    const snapshot = await api.json<{ snapshot: { id: string; short_id: string } }>(api.server('/world-restore/snapshots'), 'POST', { type: 'world' })
    await api.writeFile(marker, 'before-interruption\n')
    const proxy = await interruptRestoreAfterSafetySnapshot(owned.base_url)
    await withCleanup(async () => {
      await page.goto(`${proxy.url}/server/${owned.server_id}/world-restore`)
      await page.getByRole('button', { name: '恢复整个世界…', exact: true }).click()
      const row = page.getByText(snapshot.snapshot.short_id, { exact: true }).locator('../..')
      await row.getByRole('button', { name: '恢复', exact: true }).click()
      await page.getByRole('button', { name: '开始恢复', exact: true }).click()
      await proxy.interrupted
      await expect(page.getByText('恢复失败', { exact: true }).first()).toBeVisible()
      let history: { id: string; status: string; safety_snapshot_id: string | null; safety_snapshot_exists: boolean } | undefined
      await expect.poll(async () => {
        const data = await api.json<{ restorations: Array<{ id: string; status: string; source_snapshot_id: string; safety_snapshot_id: string | null; safety_snapshot_exists: boolean }> }>(api.server('/world-restore/restorations'))
        history = data.restorations.find(row => row.source_snapshot_id === snapshot.snapshot.id)
        return history?.status
      }, { timeout: 60_000 }).toBe('interrupted')
      expect(history?.safety_snapshot_id).toBeTruthy()
      expect(history?.safety_snapshot_exists).toBe(true)
      await api.writeFile(marker, 'after-interruption-before-rollback\n')
      expect(await readFile(path.join(owned.server_path, 'data', marker), 'utf8')).toBe('after-interruption-before-rollback\n')
      await page.goto(`/server/${owned.server_id}/world-restore`)
      await page.getByRole('button', { name: '查看恢复历史', exact: true }).click()
      const historyRow = page.getByRole('dialog', { name: '恢复历史' }).locator('div.rounded-md.border.p-3').filter({ hasText: snapshot.snapshot.id.slice(0, 8) }).filter({ hasText: history!.safety_snapshot_id!.slice(0, 8) })
      await expect(historyRow).toHaveCount(1)
      await expect(historyRow.getByText('已中断', { exact: true })).toBeVisible()
      await historyRow.getByRole('button', { name: '回滚', exact: true }).click()
      await page.getByRole('button', { name: '开始回滚', exact: true }).click()
      await expect(page.getByText('回滚完成', { exact: true })).toBeVisible({ timeout: 60_000 })
      expect((await api.file(marker)).content).toBe('before-interruption\n')
      expect(await readFile(path.join(owned.server_path, 'data', marker), 'utf8')).toBe('before-interruption\n')
    },
    { label: 'restore proxy', run: proxy.close },
    { label: 'restore marker', run: () => api.json(api.server(`/files?path=${encodeURIComponent(marker)}`), 'DELETE') },
    )
  })

  journey('an actual expired prune preview is rejected at confirmation and leaves region bytes intact', async ({ page, api, owned }) => {
    await api.stopped()
    await api.initializeMap()
    const config = await api.json<{ config_data: Record<string, unknown> }>('/api/config/modules/mcmap')
    await api.json('/api/config/modules/mcmap', 'PUT', { config_data: { ...config.config_data, prune_preview_ttl_seconds: 8 } })
    const region = path.join(owned.server_path, 'data/world/region')
    const hashes = async () => Object.fromEntries(await Promise.all((await readdir(region)).filter(name => name.endsWith('.mca')).sort().map(async name => [name, createHash('sha256').update(await readFile(path.join(region, name))).digest('hex')])))
    const before = await hashes()
    expect(Object.keys(before).length).toBeGreaterThan(0)
    try {
      await page.goto(`/server/${owned.server_id}/chunk-prune`)
      await page.getByRole('button', { name: '预览', exact: true }).click()
      const apply = page.getByRole('button', { name: '删除预览中的服务器区块' })
      await expect(apply).toBeEnabled({ timeout: 60_000 })
      await apply.click()
      const confirmation = page.getByRole('alertdialog', { name: '删除预览中的区块' })
      await expect(confirmation).toBeVisible()
      await expect.poll(async () => (await api.json<{ preview: { availability: string } }>(api.server('/chunk-prune/state'))).preview.availability, { timeout: 30_000 }).toBe('expired')
      const rejected = page.waitForResponse(response => response.request().method() === 'POST' && response.url().endsWith('/chunk-prune/apply'))
      await confirmation.getByRole('button', { name: '删除区块', exact: true }).click()
      const response = await rejected
      expect(response.status()).toBe(409)
      expect((await response.json()).detail.code).toBe('prune_preview_expired')
      await expect(page.getByText(/预览已过期/).first()).toBeVisible()
      await expect(apply).toBeDisabled()
      const state = await api.json<{ apply_task: unknown }>(api.server('/chunk-prune/state'))
      expect(state.apply_task).toBeNull()
      expect(await hashes()).toEqual(before)
    } finally {
      await api.json('/api/config/modules/mcmap', 'PUT', config)
    }
  })
  for (const { name, run } of process.env.BROWSER_REVERSE_ORDER === '1' ? [...journeys].reverse() : journeys) test(name, run)
})
