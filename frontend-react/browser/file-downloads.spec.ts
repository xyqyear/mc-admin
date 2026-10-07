import { mkdir, writeFile } from 'node:fs/promises'
import path from 'node:path'
import type { Page } from '@playwright/test'
import { test, expect, login, navigate, type OwnedApi, type OwnedEnvironment } from './fixtures'
import { withCleanup } from './cleanup'

const targetName = 'browser-download-target'
const isolated = { annotation: { type: 'shard_isolation', description: 'independent' } }
const namingTime = new Date('2026-10-06T16:42:00.123Z')
const namingTimestamp = '20261007_004200_123'

test.use({ timezoneId: 'Asia/Shanghai' })

async function nativeDirectoryPicker(page: Page) {
  await page.addInitScript(({ targetName }) => {
    Object.defineProperty(window, 'showDirectoryPicker', {
      configurable: true,
      value: async (options: { mode: string }) => {
        if (options.mode !== 'readwrite') throw new Error('Directory export must request write access')
        return (await navigator.storage.getDirectory()).getDirectoryHandle(targetName, { create: true })
      },
    })
  }, { targetName })
}

async function sourceTree(api: OwnedApi, owned: OwnedEnvironment, root: string, onCreated: () => void) {
  await api.json(api.server('/files/create'), 'POST', { path: '/', name: root, type: 'directory' })
  onCreated()
  const data = path.join(owned.server_path, 'data', root)
  await mkdir(path.join(data, 'a', 'empty'), { recursive: true })
  await mkdir(path.join(data, 'b'), { recursive: true })
  await writeFile(path.join(data, 'a', 'same.txt'), 'first original bytes\n')
  await writeFile(path.join(data, 'b', 'same.txt'), 'second original bytes\n')
  await writeFile(path.join(data, 'a', 'unselected.txt'), 'unselected original bytes\n')
}

async function exportedTree(page: Page) {
  return page.evaluate(async ({ targetName }) => {
    const storage = await navigator.storage.getDirectory()
    let target: FileSystemDirectoryHandle
    try { target = await storage.getDirectoryHandle(targetName) } catch { return { exports: [], trees: {} } }
    const exports: string[] = []
    const trees: Record<string, { files: Record<string, string>; directories: string[] }> = {}
    const visit = async (directory: FileSystemDirectoryHandle, prefix: string, tree: { files: Record<string, string>; directories: string[] }) => {
      for await (const [name, handle] of directory.entries()) {
        const relative = prefix ? `${prefix}/${name}` : name
        if (handle.kind === 'directory') {
          tree.directories.push(relative)
          await visit(handle as FileSystemDirectoryHandle, relative, tree)
        } else {
          tree.files[relative] = await (await (handle as FileSystemFileHandle).getFile()).text()
        }
      }
    }
    for await (const [name, handle] of target.entries()) {
      if (handle.kind === 'directory') {
        exports.push(name)
        const tree = { files: {} as Record<string, string>, directories: [] as string[] }
        await visit(handle as FileSystemDirectoryHandle, '', tree)
        trees[name] = { ...tree, directories: tree.directories.sort() }
      }
    }
    return { exports: exports.sort(), trees }
  }, { targetName })
}

async function removeOutput(page: Page) {
  await page.evaluate(async ({ targetName }) => {
    const storage = await navigator.storage.getDirectory()
    await storage.removeEntry(targetName, { recursive: true }).catch((error: unknown) => {
      if (!(error instanceof DOMException && error.name === 'NotFoundError')) throw error
    })
  }, { targetName })
}

async function downloadsPanel(page: Page) {
  await page.getByRole('button', { name: '任务中心', exact: true }).click()
  await page.getByRole('tab', { name: /^下载/ }).click()
}

test('recursive folder export preserves paths and empty directories while navigation continues its real downloads', isolated, async ({ page, api, owned }) => {
  const root = `browser-directory-download-${Date.now().toString(36)}`
  let created = false
  let release!: () => void
  const held = new Promise<void>((resolve) => { release = resolve })
  await nativeDirectoryPicker(page)
  await withCleanup(async () => {
    await sourceTree(api, owned, root, () => { created = true })
    await login(page, owned)
    await page.route('**/api/servers/*/files/download?*', async route => {
      if (new URL(route.request().url()).searchParams.get('path') === `${root}/a/same.txt`) await held
      await route.continue()
    })
    await page.goto(`/server/${owned.server_id}/files?q=${root}`)
    await page.getByRole('button', { name: `下载 /${root}`, exact: true }).click()
    const dialog = page.getByRole('dialog', { name: '下载到本地文件夹' })
    await expect(dialog.getByText('保留原路径', { exact: true })).toBeVisible()
    const manifestResponse = page.waitForResponse(response => response.request().method() === 'POST' && new URL(response.url()).pathname.endsWith('/files/download-manifest'))
    const contentRequest = page.waitForRequest(request => new URL(request.url()).pathname.endsWith('/files/download') && new URL(request.url()).searchParams.get('path') === `${root}/a/same.txt`)
    await page.clock.setFixedTime(namingTime)
    await dialog.getByRole('button', { name: '选择保存文件夹', exact: true }).click()
    const manifest = await manifestResponse
    await page.clock.setSystemTime(namingTime)
    expect(manifest.status()).toBe(200)
    const generation = (await manifest.json() as { server_generation: number }).server_generation
    const request = await contentRequest
    expect(new URL(request.url()).searchParams.get('expected_generation')).toBe(String(generation))
    await expect(dialog).not.toBeVisible()
    await downloadsPanel(page)
    await expect(page.getByText('正在下载 (1)', { exact: true })).toBeVisible()
    await navigate(page, `/server/${owned.server_id}`)
    await expect(page.getByText('正在下载 (1)', { exact: true })).toBeVisible()
    release()
    await expect(page.getByText('已保存 3 个文件', { exact: true })).toBeVisible()
    const output = await exportedTree(page)
    const exportName = `${owned.server_id}_${namingTimestamp}`
    expect(output.exports).toEqual([exportName])
    const originalFiles = {
      [`${root}/a/same.txt`]: 'first original bytes\n',
      [`${root}/b/same.txt`]: 'second original bytes\n',
      [`${root}/a/unselected.txt`]: 'unselected original bytes\n',
    }
    expect(output.trees[exportName].files).toEqual(originalFiles)
    expect(output.trees[exportName].directories).toContain(`${root}/a/empty`)
    await api.writeFile(`${root}/a/same.txt`, 'new export bytes\n')
    await page.goto(`/server/${owned.server_id}/files?q=${root}`)
    await page.getByRole('button', { name: `下载 /${root}`, exact: true }).click()
    const repeatedManifest = page.waitForResponse(response => response.request().method() === 'POST' && new URL(response.url()).pathname.endsWith('/files/download-manifest'))
    await page.clock.setFixedTime(namingTime)
    await page.getByRole('dialog', { name: '下载到本地文件夹' }).getByRole('button', { name: '选择保存文件夹', exact: true }).click()
    await repeatedManifest
    await page.clock.setSystemTime(namingTime)
    await downloadsPanel(page)
    await expect(page.getByText('已保存 3 个文件', { exact: true })).toHaveCount(2)
    const repeatedOutput = await exportedTree(page)
    expect(repeatedOutput.exports).toEqual([exportName, `${exportName} (2)`])
    expect(repeatedOutput.trees[exportName].files).toEqual(originalFiles)
    expect(repeatedOutput.trees[`${exportName} (2)`].files).toEqual({ ...originalFiles, [`${root}/a/same.txt`]: 'new export bytes\n' })
    expect(repeatedOutput.trees[`${exportName} (2)`].directories).toContain(`${root}/a/empty`)
  },
  { label: 'download transport', run: async () => { release(); await page.unrouteAll({ behavior: 'wait' }) } },
  { label: 'recursive download source', run: async () => { if (created) await api.deleteFile(root) } },
  { label: 'native exported directory', run: () => removeOutput(page) },
  )
})

test('advanced search flat export keeps both same-name files and excludes synthetic parent siblings', isolated, async ({ page, api, owned }) => {
  const root = `browser-flat-download-${Date.now().toString(36)}`
  let created = false
  await nativeDirectoryPicker(page)
  await withCleanup(async () => {
    await sourceTree(api, owned, root, () => { created = true })
    await login(page, owned)
    await page.goto(`/server/${owned.server_id}/files?path=${encodeURIComponent('/' + root)}`)
    await page.getByRole('button', { name: '高级搜索', exact: true }).click()
    const search = page.getByRole('dialog', { name: '高级搜索' })
    await search.getByLabel('搜索模式', { exact: true }).fill('^same[.]txt$')
    await search.getByRole('button', { name: '搜索', exact: true }).click()
    await expect(search.getByRole('checkbox', { name: '选择搜索结果 /a/same.txt', exact: true })).toBeVisible()
    await expect(search.getByRole('checkbox', { name: '选择搜索结果 /a', exact: true })).toHaveCount(0)
    await search.getByRole('checkbox', { name: '选择搜索结果 /a/same.txt', exact: true }).click()
    await search.getByRole('checkbox', { name: '选择搜索结果 /b/same.txt', exact: true }).click()
    const snapshotPosts: string[] = []
    page.on('request', request => {
      if (request.method() === 'POST' && new URL(request.url()).pathname === '/api/snapshots') snapshotPosts.push(request.url())
    })
    await search.getByRole('button', { name: '创建快照', exact: true }).click()
    const snapshot = page.getByRole('dialog', { name: '确认创建快照' })
    await expect(snapshot).toBeVisible()
    await expect(snapshot.getByText('确定要为 选中的 2 个条目 创建快照吗？忽略目录会被跳过。', { exact: true })).toBeVisible()
    await snapshot.getByRole('button', { name: '取消', exact: true }).click()
    await expect(snapshot).not.toBeVisible()
    await expect(search).toBeVisible()
    await expect(search.getByRole('checkbox', { name: '选择搜索结果 /a/same.txt', exact: true })).toBeChecked()
    await expect(search.getByRole('checkbox', { name: '选择搜索结果 /b/same.txt', exact: true })).toBeChecked()
    expect(snapshotPosts).toEqual([])
    await search.getByRole('button', { name: '下载到文件夹', exact: true }).click()
    const download = page.getByRole('dialog', { name: '下载到本地文件夹' })
    await download.getByLabel('文件组织方式', { exact: true }).click()
    await page.getByRole('option', { name: '平铺文件', exact: true }).click()
    const manifestRequest = page.waitForRequest(request => request.method() === 'POST' && new URL(request.url()).pathname.endsWith('/files/download-manifest'))
    await page.clock.setFixedTime(namingTime)
    await download.getByRole('button', { name: '选择保存文件夹', exact: true }).click()
    const request = await manifestRequest
    await page.clock.setSystemTime(namingTime)
    expect((request.postDataJSON() as { paths: string[] }).paths.sort()).toEqual([`${root}/a/same.txt`, `${root}/b/same.txt`])
    await expect(download).not.toBeVisible()
    await page.keyboard.press('Escape')
    await expect(search).not.toBeVisible()
    await downloadsPanel(page)
    await expect(page.getByText('已保存 2 个文件', { exact: true })).toBeVisible()
    const output = await exportedTree(page)
    const exportName = `${owned.server_id}_${namingTimestamp}`
    expect(output.exports).toEqual([exportName])
    expect(output.trees[exportName].files).toEqual({ 'same.txt': 'first original bytes\n', 'same (2).txt': 'second original bytes\n' })
    expect(output.trees[exportName].directories).toEqual([])
    await page.getByRole('button', { name: /文件夹下载（2 个目标）/ }).click()
    await expect(page.getByRole('dialog').filter({ hasText: '下载详情' }).getByText(`${root}/b/same.txt → same (2).txt`)).toBeVisible()
    expect((await api.file(`${root}/a/unselected.txt`)).content).toBe('unselected original bytes\n')
  },
  { label: 'flat download source', run: async () => { if (created) await api.deleteFile(root) } },
  { label: 'native exported directory', run: () => removeOutput(page) },
  )
})

test('unsupported direct download controls remain visible with version-free browser feedback and available packing', isolated, async ({ page, api, owned }) => {
  const root = `browser-unsupported-download-${Date.now().toString(36)}`
  let created = false
  await page.addInitScript(() => Object.defineProperty(window, 'showDirectoryPicker', { configurable: true, value: undefined }))
  await withCleanup(async () => {
    await api.json(api.server('/files/create'), 'POST', { path: '/', name: root, type: 'directory' })
    created = true
    await login(page, owned)
    await page.goto(`/server/${owned.server_id}/files?q=${root}`)
    const folderDownload = page.getByRole('button', { name: `下载 /${root}`, exact: true })
    await expect(folderDownload).toBeVisible()
    await expect(folderDownload).toBeDisabled()
    await folderDownload.locator('..').hover()
    await expect(page.locator('[data-slot="tooltip-content"]:visible')).toHaveText('当前浏览器不支持直接下载到文件夹，仅支持 Chrome 和 Edge。')
    await page.getByRole('checkbox', { name: `选择 /${root}`, exact: true }).click()
    const batchDownload = page.getByRole('button', { name: '下载到文件夹', exact: true })
    await expect(batchDownload).toBeVisible()
    await expect(batchDownload).toBeDisabled()
    await batchDownload.locator('..').hover()
    await expect(page.locator('[data-slot="tooltip-content"]:visible')).toHaveText('当前浏览器不支持直接下载到文件夹，仅支持 Chrome 和 Edge。')
    await expect(page.getByRole('button', { name: '打包所选', exact: true })).toBeEnabled()
  }, { label: 'unsupported download source', run: async () => { if (created) await api.deleteFile(root) } })
})
