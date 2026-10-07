import type { Page } from '@playwright/test'
import { test, expect, login, navigate } from './fixtures'

const validCompose = `services:
  mc:
    image: itzg/minecraft-server:java25
    container_name: mc-editor-validation
    environment:
      EULA: true
      VERSION: "1.21.11"
      TYPE: VANILLA
      TZ: Asia/Shanghai
      MAX_MEMORY: 1G
      ENABLE_RCON: true
      RCON_PASSWORD: editor-validation
      ENABLE_QUERY: false
    ports:
      - "25565:25565"
      - "25575:25575"
    volumes:
      - "./data:/data"
    stdin_open: true
    tty: true
    restart: "no"
`

async function showHover(page: Page) {
  await page.keyboard.press('ControlOrMeta+k')
  await page.keyboard.press('ControlOrMeta+i')
}

async function lineEnd(page: Page, index: number) {
  await page.keyboard.press('ControlOrMeta+Home')
  for (let line = 0; line < index; line++) await page.keyboard.press('ArrowDown')
  await page.keyboard.press('End')
}

async function pasteEditor(page: Page, value: string) {
  const editor = page.locator('.monaco-editor').first()
  await expect(editor).toBeVisible()
  await editor.locator('.view-lines').click({ position: { x: 20, y: 10 } })
  await expect(editor.getByRole('textbox', { name: 'Editor content', exact: true })).toBeFocused()
  await page.keyboard.press('ControlOrMeta+Home')
  await page.keyboard.press('ControlOrMeta+A')
  await page.evaluate(text => navigator.clipboard.writeText(text), value)
  await page.keyboard.press('ControlOrMeta+V')
  // Monaco cancels asynchronous paste if the selection moves before it finishes.
  const pastedEnding = value.trim() === 'services: ]'
    ? /^\s*services:\s*\]\s*$/
    : /^\s*restart:\s*["']?no["']?\s*$/
  await expect(editor.locator('.view-line').filter({ hasText: pastedEnding })).toBeVisible()
  const unfinishedProperty = editor.locator('.view-line').filter({ hasText: /^\s*MEM\s*$/ })
  if (value.split('\n').some(line => line.trim() === 'MEM')) {
    await expect(unfinishedProperty).toBeVisible()
  } else {
    await expect(unfinishedProperty).toHaveCount(0)
  }
  await page.keyboard.press('ControlOrMeta+Home')
}

async function verifyYamlWorker(page: Page) {
  const editor = page.locator('.monaco-editor').first()
  await pasteEditor(page, 'services: ]\n')
  await expect(editor.locator('.squiggly-error').first()).toBeVisible()
  await page.keyboard.press('F8')
  await showHover(page)
  await expect(editor.locator('.monaco-hover:visible')).toBeVisible()
  await expect(editor.locator('.monaco-hover:visible')).toContainText(/unexpected.*(?:flow|token|\])/i)
  await page.keyboard.press('Escape')

  await pasteEditor(page, validCompose)
  await expect(editor.locator('.squiggly-error')).toHaveCount(0)
  const eulaLine = validCompose.split('\n').findIndex(line => line.includes('EULA:'))
  await lineEnd(page, eulaLine)
  await page.keyboard.press('Home')
  await page.keyboard.press('ArrowRight')
  await page.keyboard.press('ArrowRight')
  await showHover(page)
  await expect(editor.locator('.monaco-hover:visible')).toContainText('Minecraft 最终用户许可协议')
  await page.keyboard.press('Escape')

  const completionDraft = validCompose.replace('      MAX_MEMORY: 1G\n', '      MAX_MEMORY: 1G\n      MEM\n')
  await pasteEditor(page, completionDraft)
  const completionLine = completionDraft.split('\n').findIndex(line => line.trim() === 'MEM')
  await lineEnd(page, completionLine)
  await page.keyboard.press('Control+Space')
  const suggestions = editor.locator('.suggest-widget')
  await expect(suggestions).toBeVisible()
  await expect(suggestions.getByText('MEMORY', { exact: true })).toBeVisible()
  await page.keyboard.press('Escape')
  await pasteEditor(page, validCompose)
  await expect(editor.locator('.squiggly-error')).toHaveCount(0)
}

async function openTemplateDraft(page: Page) {
  await page.getByRole('button', { name: '服务器模板', exact: true }).click()
  await expect(page).toHaveURL(/\/templates$/)
  await page.getByRole('button', { name: '新建模板', exact: true }).click()
  await expect(page).toHaveURL(/\/templates\/new$/)
}

test('Compose and template YAML workers validate and complete after navigation', { annotation: { type: 'shard_isolation', description: 'independent' } }, async ({ page, api, owned }) => {
  await page.context().grantPermissions(['clipboard-read', 'clipboard-write'], { origin: new URL(owned.base_url).origin })
  const workerErrors: string[] = []
  const workerFailure = /Missing requestHandler|monaco|yaml|worker/i
  page.on('pageerror', error => {
    const detail = error.stack ?? error.message
    if (workerFailure.test(detail)) workerErrors.push(detail)
  })
  page.on('console', message => {
    if (message.type() === 'error' && workerFailure.test(message.text())) workerErrors.push(message.text())
  })
  const schemaResponses: number[] = []
  page.on('response', response => {
    if (new URL(response.url()).pathname === '/static/mc-server-compose-schema.json') schemaResponses.push(response.status())
  })
  const original = await api.json<{ yaml_content: string; version: string }>(api.server('/compose'))
  const originalTemplates = await api.json('/api/templates/')
  await login(page, owned)
  await page.goto(`/server/${owned.server_id}/compose`)
  await verifyYamlWorker(page)
  await openTemplateDraft(page)
  await verifyYamlWorker(page)
  await page.getByRole('button', { name: '服务器管理', exact: true }).click()
  const serverLabel = owned.server_id.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  await page.locator('[data-sidebar="menu-sub-button"]').filter({ hasText: new RegExp(`^${serverLabel}$`) }).click()
  await navigate(page, `/server/${owned.server_id}/compose`)
  await expect(page.getByText('Docker Compose 配置', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: '提交并重建', exact: true })).toBeEnabled()
  await expect(page.locator('.monaco-editor').first().locator('.view-lines')).toContainText(owned.server_id)
  await verifyYamlWorker(page)
  await openTemplateDraft(page)
  await verifyYamlWorker(page)
  await page.getByRole('button', { name: '服务器总览', exact: true }).click()
  await expect(page).toHaveURL(/\/overview$/)

  expect(schemaResponses).toContain(200)
  expect(workerErrors).toEqual([])
  expect(await api.json(api.server('/compose'))).toEqual(original)
  expect(await api.json('/api/templates/')).toEqual(originalTemplates)
})
