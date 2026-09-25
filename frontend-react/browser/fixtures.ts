import { chown, copyFile, mkdir, readFile, realpath, stat } from 'node:fs/promises'
import { createHash } from 'node:crypto'
import path from 'node:path'
import { test as base, expect, type Page } from '@playwright/test'
import { NetworkObservation } from './observation'

export interface OwnedEnvironment {
  base_url: string
  server_id: string
  server_path: string
  username: string
  password: string
  master_token: string
  backend_container: string
  run_id: string
  image_id: string
  environment_id: string
  manifest_path: string
}

async function ownedEnvironment(): Promise<OwnedEnvironment> {
  const source = process.env.MC_ADMIN_BROWSER_FIXTURE
  if (!source) throw new Error('Run browser tests through mc-admin-e2e browser; no attach mode is supported.')
  const document: unknown = JSON.parse(await readFile(source, 'utf8'))
  const fields: Array<keyof OwnedEnvironment> = ['base_url', 'server_id', 'server_path', 'username', 'password', 'master_token', 'backend_container', 'run_id', 'image_id', 'environment_id', 'manifest_path']
  if (!document || typeof document !== 'object' || fields.some(field => !(field in document) || typeof document[field as keyof typeof document] !== 'string' || !document[field as keyof typeof document])) throw new Error('The owned browser fixture is incomplete.')
  const fixture = document as OwnedEnvironment
  const url = new URL(fixture.base_url)
  if (url.protocol !== 'http:' || !['127.0.0.1', 'localhost'].includes(url.hostname)) throw new Error('The browser fixture must be an owned local deployment.')
  const runtime = await realpath(path.join(path.dirname(fixture.manifest_path), 'runtime'))
  const sourcePath = await realpath(source)
  const serverPath = await realpath(fixture.server_path)
  if (![sourcePath, serverPath].every(candidate => candidate.startsWith(runtime + path.sep))) throw new Error('Browser fixture paths must belong to the recorded runtime directory.')
  if ((await stat(source)).mode & 0o077) throw new Error('Browser fixture credentials must have private file permissions.')
  return fixture
}

export class OwnedApi {
  clientSource: Record<string, unknown> | undefined
  constructor(readonly environment: OwnedEnvironment) {}
  server(suffix: string) { return `/api/servers/${this.environment.server_id}${suffix}` }

  async response(url: string, method = 'GET', body?: unknown) {
    return fetch(new URL(url, this.environment.base_url), {
      method,
      headers: { Authorization: `Bearer ${this.environment.master_token}`, ...(body === undefined ? {} : { 'Content-Type': 'application/json' }) },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: AbortSignal.timeout(150_000),
    })
  }

  async json<T = Record<string, unknown>>(url: string, method = 'GET', body?: unknown, status = 200): Promise<T> {
    const response = await this.response(url, method, body)
    expect(response.status, `${method} ${new URL(url, this.environment.base_url).pathname}`).toBe(status)
    return response.json() as Promise<T>
  }

  async operation(action: string) {
    await this.json(this.server('/operations'), 'POST', { action })
  }

  async stopped() {
    const current = await this.json<{ status: string }>(this.server('/status'))
    if (!['created', 'exists'].includes(current.status.toLowerCase())) await this.operation('stop')
    await expect.poll(async () => (await this.json<{ status: string }>(this.server('/status'))).status.toLowerCase(), { timeout: 60_000 }).toMatch(/^(created|exists)$/)
  }

  async running() {
    const current = await this.json<{ status: string }>(this.server('/status'))
    if (!['healthy', 'running', 'starting'].includes(current.status.toLowerCase())) await this.operation('up')
    await expect.poll(async () => (await this.json<{ status: string }>(this.server('/status'))).status.toLowerCase(), { timeout: 120_000 }).toBe('healthy')
  }

  async task(id: string, requireSuccess = true) {
    let result: { status: string; error?: string; result?: Record<string, unknown> } | undefined
    await expect.poll(async () => {
      result = await this.json(`/api/tasks/${id}`)
      return result?.status
    }, { timeout: 120_000, intervals: [250, 500, 1000] }).toMatch(/^(completed|failed|cancelled)$/)
    if (requireSuccess) expect(result?.status, `task ${id} must complete`).toBe('completed')
    return result!
  }

  async file(relativePath: string) {
    return this.json<{ content: string }>(this.server(`/files/content?path=${encodeURIComponent(relativePath)}`))
  }

  async writeFile(relativePath: string, content: string) {
    await this.json(this.server(`/files/content?path=${encodeURIComponent(relativePath)}`), 'POST', { content })
  }

  async initializeMap() {
    const status = await this.json<{ palette_current: boolean }>(this.server('/map/status'))
    if (status.palette_current) return
    const metadataPath = process.env.MC_ADMIN_BROWSER_CLIENT_METADATA
    if (metadataPath) {
      const metadata = JSON.parse(await readFile(metadataPath, 'utf8')) as { path: string; url: string; version: string; sha1: string; size: number }
      if (new URL(metadata.url).hostname !== 'piston-data.mojang.com' || !/^[a-f0-9]{40}$/.test(metadata.sha1)) throw new Error('The optional Minecraft client must have official download provenance.')
      const bytes = await readFile(metadata.path)
      if (bytes.length !== metadata.size || createHash('sha1').update(bytes).digest('hex') !== metadata.sha1) throw new Error('The optional official Minecraft client failed integrity verification.')
      const data = path.join(this.environment.server_path, 'data')
      const cache = path.join(data, '.mcmap')
      await mkdir(cache, { recursive: true })
      if (!(await realpath(cache)).startsWith((await realpath(data)) + path.sep)) throw new Error('The Minecraft cache must stay inside the owned server data directory.')
      const destination = path.join(cache, 'client.jar')
      await copyFile(metadata.path, destination)
      const owner = await stat(data)
      if (process.getuid?.() === 0) {
        await chown(cache, owner.uid, owner.gid)
        await chown(destination, owner.uid, owner.gid)
      }
      this.clientSource = { version: metadata.version, url: metadata.url, sha1: metadata.sha1, bytes: metadata.size }
    }
    const response = await this.response(this.server('/map/initialize'), 'POST', {})
    expect(response.status).toBe(200)
    const body = await response.text()
    const events = body.split('\n').filter(line => line.startsWith('data:')).map(line => JSON.parse(line.slice(5)))
    expect(events.at(-1)?.stage, 'real map initialization must complete').toBe('complete')
    expect((await this.json<{ palette_current: boolean }>(this.server('/map/status'))).palette_current).toBe(true)
  }
}

export const test = base.extend<{ api: OwnedApi; observation: NetworkObservation }, { owned: OwnedEnvironment }>({
  owned: [async ({ playwright }, use) => { void playwright; await use(await ownedEnvironment()) }, { scope: 'worker' }],
  api: async ({ owned }, use) => {
    const api = new OwnedApi(owned)
    const original = (await api.json<{ status: string }>(api.server('/status'))).status.toLowerCase()
    try { await use(api) }
    finally {
      if (['healthy', 'running', 'starting'].includes(original)) await api.running()
      else await api.stopped()
    }
  },
  observation: [async ({ page, owned }, use, testInfo) => {
    const observation = new NetworkObservation(page, owned)
    await use(observation)
    await testInfo.attach('browser-observation.json', { body: JSON.stringify(await observation.finish(), null, 2), contentType: 'application/json' })
  }, { auto: true }],
})
export { expect }

export async function login(page: Page, owned: OwnedEnvironment) {
  await page.goto('/login')
  await page.getByPlaceholder('请输入用户名').fill(owned.username)
  await page.getByPlaceholder('请输入密码').fill(owned.password)
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await expect(page.getByRole('button', { name: '退出登录' })).toBeVisible()
}

export async function editorValue(page: Page, value: string) {
  const editor = page.locator('.monaco-editor').first()
  await expect(editor).toBeVisible()
  await editor.locator('.view-lines').click({ position: { x: 20, y: 10 } })
  await page.keyboard.press('ControlOrMeta+Home')
  await page.keyboard.press('ControlOrMeta+A')
  if (value) await page.keyboard.insertText(value)
  else await page.keyboard.press('Backspace')
  await page.keyboard.press('ControlOrMeta+Home')
}

export async function navigate(page: Page, pathname: string) {
  const label = pathname.endsWith('/compose') ? '设置' : pathname.endsWith('/files') ? '文件' : '概览'
  await page.locator('[data-sidebar="menu-sub-button"]').filter({ hasText: new RegExp(`^${label}$`) }).click()
  await expect(page).toHaveURL(new RegExp(pathname.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '$'))
}
