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
  const completedFilename = `${filename}.deleted`
  await api.json(api.server('/files/create'), 'POST', { path: '/', name: completedFilename, type: 'file' })
  const completedDeletion = await api.json<{ task_id: string }>(api.server('/files/delete-batch'), 'POST', { paths: [completedFilename] }, 202)
  await api.task(completedDeletion.task_id)
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
    await dialog.getByRole('button', { name: '查看任务', exact: true }).click()
    const taskCenter = page.getByRole('dialog', { name: '任务中心', exact: true })
    await expect(taskCenter).toBeVisible()
    await taskCenter.getByRole('tab', { name: /^下载/ }).click()
    await taskCenter.getByRole('tab', { name: /^后台任务/ }).click()
    await expect(taskCenter.getByTitle('创建快照', { exact: true }).first()).toBeVisible()
    await taskCenter.getByTitle(`批量删除 ${owned.server_id} 的 1 项`, { exact: true }).click()
    await page.getByRole('button', { name: '查看结果', exact: true }).click()
    await page.getByText('完整结果数据', { exact: true }).click()
    await expect(page.locator('pre').filter({ hasText: completedFilename })).toBeVisible()
    await page.keyboard.press('Escape')
    await expect.poll(() => taskCenter.evaluate(element => element.contains(document.activeElement))).toBe(true)
    await taskCenter.getByRole('button', { name: '关闭任务中心', exact: true }).click()
    await expect(taskCenter).toBeHidden()
    await expect(dialog).toBeVisible()
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

test('map reload streams stages without per-progress task detail reads', { annotation: { type: 'shard_isolation', description: 'independent' } }, async ({ page, api, owned }) => {
  await api.initializeMap()
  const observations = new Map<string, { liveStages: Set<string>; terminal: boolean; runningResult: boolean }>()
  let taskId = ''
  const detailPaths: string[] = []
  let discoveryReads = 0
  let streamCount = 0
  const proxy = await createTaskObservationFault(owned.base_url, event => {
    const tasks = event.type === 'upsert' ? [event.task] : event.type === 'snapshot' ? event.tasks : []
    if (!Array.isArray(tasks)) return
    for (const value of tasks) {
      if (!value || typeof value !== 'object') continue
      const task = value as { task_id: string; task_type: string; status: string; progress_details?: { kind: string; stages?: Record<string, unknown> }; result_included: boolean }
      if (task.task_type !== 'map_initialize') continue
      const observed = observations.get(task.task_id) ?? { liveStages: new Set<string>(), terminal: false, runningResult: false }
      if (task.status === 'running') {
        observed.runningResult ||= task.result_included
        if (task.progress_details?.kind === 'map') Object.keys(task.progress_details.stages ?? {}).forEach(stage => observed.liveStages.add(stage))
      }
      if (task.status === 'completed') observed.terminal = task.result_included
      observations.set(task.task_id, observed)
    }
  })
  const observe = (request: Request) => {
    const pathname = new URL(request.url()).pathname
    if (request.method() !== 'GET') return
    if (/^\/api\/tasks\/[^/]+$/.test(pathname) && pathname !== '/api/tasks/events') detailPaths.push(pathname)
    if (pathname === '/api/tasks/events') streamCount++
    if (pathname === '/api/operations/changes' || pathname === '/api/snapshots/restorations/active' || pathname.endsWith('/chunk-prune/state')) discoveryReads++
  }
  await withCleanup(async () => {
    await login(page, owned)
    page.on('request', observe)
    await page.goto(`${proxy.url}/server/${owned.server_id}/chunk-prune`)
    const acceptance = page.waitForResponse(response => response.request().method() === 'POST' && new URL(response.url()).pathname === api.server('/map/initialize'))
    await page.getByRole('button', { name: '重载渲染前置', exact: true }).click()
    const accepted = await acceptance
    expect(accepted.status()).toBe(202)
    taskId = ((await accepted.json()) as { task_id: string }).task_id
    const dialog = page.getByRole('dialog', { name: '正在重载渲染前置' })
    await expect(dialog).toBeVisible()
    await expect.poll(() => observations.get(taskId)?.liveStages.has('client'), { timeout: 90_000 }).toBe(true)
    await expect.poll(() => observations.get(taskId)?.liveStages.has('palette'), { timeout: 120_000 }).toBe(true)
    await expect.poll(() => observations.get(taskId)?.terminal, { timeout: 120_000 }).toBe(true)
    await expect(dialog).toBeHidden()
    expect(observations.get(taskId)?.runningResult).toBe(false)
    expect(detailPaths.filter(pathname => pathname === `/api/tasks/${taskId}`).length).toBeLessThanOrEqual(1)
    expect(discoveryReads).toBe(0)
    expect(streamCount).toBe(1)
    expect((await api.json<{ palette_current: boolean }>(api.server('/map/status'))).palette_current).toBe(true)
    const result = await api.task(taskId)
    expect((result.result?.stages as Record<string, { phase: string }>).palette.phase).toBe('done')
  }, { label: 'map observation proxy', run: async () => { page.off('request', observe); await proxy.close() } })
})


test('task center retries a real large retained result without submitting the operation again', { annotation: { type: 'shard_isolation', description: 'independent' } }, async ({ page, api, owned }) => {
  const root = `browser-task-results-${Date.now().toString(36)}`
  const names = Array.from({ length: 70 }, (_, index) => `item-${String(index).padStart(3, '0')}-${'x'.repeat(190)}.txt`)
  let created = false
  let taskId = ''
  let reads = 0
  let allowRead = false
  let operationWrites = 0
  const countWrite = (request: Request) => {
    if (request.method() === 'POST' && new URL(request.url()).pathname.endsWith('/files/delete-batch')) operationWrites++
  }
  await withCleanup(async () => {
    await api.json(api.server('/files/create'), 'POST', { path: '/', name: root, type: 'directory' })
    created = true
    for (const name of names) await api.json(api.server('/files/create'), 'POST', { path: '/' + root, name, type: 'file' })
    const accepted = await api.json<{ task_id: string }>(api.server('/files/delete-batch'), 'POST', { paths: names.map(name => `${root}/${name}`) }, 202)
    taskId = accepted.task_id
    const terminal = await api.task(taskId)
    expect(terminal.result).toMatchObject({ deleted: 70, failed: 0, pending: 0 })
    expect(Buffer.byteLength(JSON.stringify(terminal.result))).toBeGreaterThan(16 * 1024)
    await login(page, owned)
    page.on('request', countWrite)
    await page.route(`**/api/tasks/${taskId}`, async route => {
      reads++
      if (allowRead) await route.continue()
      else await route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ detail: '临时无法读取结果' }) })
    })
    await page.goto(`/server/${owned.server_id}/files?path=/${root}`)
    await page.getByRole('button', { name: '任务中心', exact: true }).click()
    await page.getByTitle(`批量删除 ${owned.server_id} 的 70 项`, { exact: true }).click()
    expect(reads).toBe(0)
    await page.getByRole('button', { name: '查看结果', exact: true }).click()
    const retry = page.getByRole('button', { name: '重试读取结果', exact: true })
    await expect(retry).toBeVisible()
    await expect(page.getByText('任务已结束，但完整结果读取失败。请重试读取，无需重新执行任务。', { exact: true })).toBeVisible()
    const failedReads = reads
    allowRead = true
    await retry.click()
    await page.getByText('完整结果数据', { exact: true }).click()
    await expect(page.locator('pre').filter({ hasText: `${root}/${names[0]}` })).toBeVisible()
    expect(reads).toBe(failedReads + 1)
    expect(operationWrites).toBe(0)
    const listing = await api.json<{ items: Array<{ name: string }> }>(api.server(`/files?path=${encodeURIComponent(root)}`))
    expect(listing.items).toEqual([])
  }, { label: 'large task result source', run: async () => {
    page.off('request', countWrite)
    if (taskId) await api.task(taskId, false)
    if (created) await api.deleteFile(root)
  } })
})
