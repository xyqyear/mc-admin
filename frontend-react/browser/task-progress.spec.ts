import { readFile } from 'node:fs/promises'
import path from 'node:path'
import type { Request, Response } from '@playwright/test'
import { test, expect, login } from './fixtures'
import { withCleanup } from './cleanup'
import { holdSnapshotBackup } from './snapshotWorker'
import { createTaskObservationFault } from './streamFault'

test('shared task SSE preserves snapshot guards through disconnect and recovers the actual result', { annotation: { type: 'shard_isolation', description: 'independent' } }, async ({ page, api, owned }) => {
  const filename = `browser-task-sse-${Date.now().toString(36)}.txt`
  const content = 'snapshot SSE source bytes\n'
  await api.json(api.server('/files/create'), 'POST', { path: '/', name: filename, type: 'file' })
  await api.writeFile(filename, content)
  const proxy = await createTaskObservationFault(owned.base_url)
  let taskId = ''
  let detailReads = 0
  const streams: Response[] = []
  let worker: ReturnType<typeof holdSnapshotBackup> | undefined
  const observeResponse = (response: Response) => {
    if (new URL(response.url()).pathname === '/api/tasks/events' && response.status() === 200) streams.push(response)
  }
  const observeRequest = (request: Request) => {
    if (taskId && request.method() === 'GET' && new URL(request.url()).pathname === `/api/tasks/${taskId}`) detailReads++
  }
  await withCleanup(async () => {
    const authenticatedStream = page.waitForResponse(response => new URL(response.url()).pathname === '/api/tasks/events' && response.status() === 200)
    await login(page, owned)
    await authenticatedStream
    page.on('response', observeResponse)
    page.on('request', observeRequest)
    const connected = page.waitForResponse(response => new URL(response.url()).pathname === '/api/tasks/events' && response.status() === 200)
    await page.goto(`${proxy.url}/server/${owned.server_id}/files?q=${encodeURIComponent(filename)}`)
    const stream = await connected
    expect(stream.headers()['content-type']).toContain('text/event-stream')
    expect(stream.headers()['cache-control']).toBe('no-cache')
    expect(stream.headers()['x-accel-buffering']).toBe('no')
    await page.getByRole('button', { name: `为 ${filename} 创建快照`, exact: true }).click()
    const dialog = page.getByRole('dialog', { name: '确认创建快照', exact: true })
    worker = holdSnapshotBackup(owned)
    const acceptedResponse = page.waitForResponse(response => response.request().method() === 'POST' && new URL(response.url()).pathname === '/api/snapshots')
    await dialog.getByRole('button', { name: '创建快照', exact: true }).click()
    const accepted = await acceptedResponse
    expect(accepted.status()).toBe(202)
    taskId = ((await accepted.json()) as { task_id: string }).task_id
    await worker.ready
    await expect(dialog.getByText('正在读取文件并创建快照', { exact: true })).toBeVisible()
    await expect(dialog.getByRole('button', { name: '取消', exact: true })).toBeDisabled()
    await page.keyboard.press('Escape')
    await expect(dialog).toBeVisible()
    const initialReads = detailReads
    await page.waitForTimeout(3200)
    expect(detailReads).toBe(initialReads)
    expect(streams).toHaveLength(1)
    expect((await api.json<{ status: string }>(`/api/tasks/${taskId}`)).status).toBe('running')
    const disconnected = page.waitForEvent('requestfailed', request => new URL(request.url()).pathname === '/api/tasks/events')
    proxy.disconnect(taskId)
    await disconnected
    await proxy.interrupted
    await worker.release()
    const terminal = await api.task(taskId)
    const result = terminal.result as { snapshot: { id: string } }
    expect(result.snapshot.id).toMatch(/^[0-9a-f]{64}$/)
    await expect(dialog).toBeVisible()
    await expect(dialog.getByRole('button', { name: '取消', exact: true })).toBeDisabled()
    const reconnected = page.waitForResponse(response => new URL(response.url()).pathname === '/api/tasks/events' && response.status() === 200, { timeout: 45_000 })
    proxy.resume()
    await reconnected
    await expect(dialog).toBeHidden({ timeout: 30_000 })
    expect((await api.file(filename)).content).toBe(content)
    expect(await readFile(path.join(owned.server_path, 'data', filename), 'utf8')).toBe(content)
    const snapshots = await api.json<{ snapshots: Array<{ id: string }> }>('/api/snapshots')
    expect(snapshots.snapshots.some(snapshot => snapshot.id === result.snapshot.id)).toBe(true)
  },
  { label: 'browser task connection', run: async () => {
    page.off('response', observeResponse)
    page.off('request', observeRequest)
    await proxy.close()
  } },
  { label: 'snapshot worker', run: async () => {
    await worker?.release()
    if (taskId) await api.task(taskId, false)
  } },
  { label: 'snapshot source', run: () => api.deleteFile(filename) },
  )
})
