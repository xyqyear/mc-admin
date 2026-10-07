import { readFile } from 'node:fs/promises'
import path from 'node:path'
import { test, expect, login } from './fixtures'
import { withCleanup } from './cleanup'

test.use({ timezoneId: 'Asia/Shanghai' })

test('multiple checked files share snapshot recovery, packing and deletion while unselected bytes stay intact', { annotation: { type: 'shard_isolation', description: 'independent' } }, async ({ page, api, owned }) => {
  const root = 'browser-batch-files'
  let created = false
  let archive: string | undefined
  await withCleanup(async () => {
    await api.json(api.server('/files/create'), 'POST', { path: '/', name: root, type: 'directory' })
    created = true
    for (const name of ['a.txt', 'b.txt', 'keep.txt']) {
      await api.json(api.server('/files/create'), 'POST', { path: '/' + root, name, type: 'file' })
      await api.writeFile(root + '/' + name, `${name} snapshot bytes\n`)
    }
    await login(page, owned)
    await page.goto(`/server/${owned.server_id}/files?path=/${root}`)
    for (const name of ['a.txt', 'b.txt']) await page.getByRole('checkbox', { name: `选择 /${root}/${name}`, exact: true }).click()
    const creationResponse = page.waitForResponse(response => response.request().method() === 'POST' && new URL(response.url()).pathname === '/api/snapshots')
    await page.getByRole('button', { name: '创建快照', exact: true }).click()
    const creation = page.getByRole('dialog', { name: '确认创建快照' })
    await creation.getByLabel('快照备注（可选）').fill('浏览器多选恢复')
    await creation.getByRole('button', { name: '创建快照', exact: true }).click()
    const accepted = await creationResponse
    expect(accepted.request().postDataJSON()).toEqual({ scope: { kind: 'paths', server_id: owned.server_id, paths: [`${root}/a.txt`, `${root}/b.txt`] }, note: '浏览器多选恢复' })
    const snapshot = (await api.task((await accepted.json()).task_id)).result as { snapshot: { id: string; short_id: string } }
    await expect(creation).toBeHidden()
    await api.writeFile(root + '/a.txt', 'changed a\n')
    await api.writeFile(root + '/b.txt', 'changed b\n')
    await api.writeFile(root + '/keep.txt', 'unselected keep\n')
    await page.getByRole('button', { name: '快照恢复', exact: true }).click()
    const picker = page.getByRole('dialog', { name: /选择要恢复的快照/ })
    const row = picker.getByRole('row').filter({ hasText: snapshot.snapshot.short_id })
    await expect(row.getByText('浏览器多选恢复', { exact: true })).toBeVisible()
    const restoreResponse = page.waitForResponse(response => response.request().method() === 'POST' && new URL(response.url()).pathname === '/api/snapshots/restorations')
    await row.getByRole('button', { name: '恢复', exact: true }).click()
    await api.task((await (await restoreResponse).json()).task_id)
    await expect(picker.getByText('恢复完成', { exact: true }).first()).toBeVisible()
    await picker.getByRole('button', { name: '关闭', exact: true }).click()
    expect((await api.file(root + '/a.txt')).content).toBe('a.txt snapshot bytes\n')
    expect((await api.file(root + '/b.txt')).content).toBe('b.txt snapshot bytes\n')
    expect((await api.file(root + '/keep.txt')).content).toBe('unselected keep\n')
    const namingTime = new Date('2026-10-06T16:42:00.123Z')
    await page.clock.setFixedTime(namingTime)
    const packResponse = page.waitForResponse(response => response.request().method() === 'POST' && new URL(response.url()).pathname === '/api/archive/compress')
    await page.getByRole('button', { name: '打包所选', exact: true }).click()
    await page.getByRole('button', { name: '开始压缩', exact: true }).click()
    const packed = await packResponse
    await page.clock.setSystemTime(namingTime)
    expect(packed.request().postDataJSON()).toEqual({ server_id: owned.server_id, paths: [`/${root}/a.txt`, `/${root}/b.txt`], client_timestamp: '20261007_004200_123' })
    archive = (await api.task((await packed.json()).task_id)).result?.filename as string
    expect(archive).toBe(`${owned.server_id}_20261007_004200_123.7z`)
    await expect(page.getByRole('dialog', { name: '压缩完成' }).getByText(archive, { exact: true })).toBeVisible()
    await page.keyboard.press('Escape')
    const deletionResponse = page.waitForResponse(response => response.request().method() === 'POST' && new URL(response.url()).pathname.endsWith('/files/delete-batch'))
    await page.getByRole('button', { name: '批量删除', exact: true }).click()
    await page.getByRole('alertdialog', { name: '确认批量删除' }).getByRole('button', { name: '删除', exact: true }).click()
    const deleted = await deletionResponse
    expect(deleted.request().postDataJSON()).toEqual({ paths: [`/${root}/a.txt`, `/${root}/b.txt`] })
    const outcome = await api.task((await deleted.json()).task_id)
    expect(outcome.result).toMatchObject({ deleted: 2, failed: 0, pending: 0 })
    await expect(page.getByRole('checkbox', { name: `选择 /${root}/a.txt`, exact: true })).toBeHidden()
    await expect(page.getByRole('checkbox', { name: `选择 /${root}/b.txt`, exact: true })).toBeHidden()
    expect(await readFile(path.join(owned.server_path, 'data', root, 'keep.txt'), 'utf8')).toBe('unselected keep\n')
  },
  { label: 'batch files', run: async () => { if (created) await api.deleteFile(root) } },
  { label: 'batch archive', run: async () => {
    if (!archive) return
    const accepted = await api.json<{ task_id: string }>('/api/archive?path=' + encodeURIComponent('/' + archive), 'DELETE', undefined, 202)
    await api.task(accepted.task_id)
  } })
})
