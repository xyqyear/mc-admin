import { readFileSync } from 'node:fs'
import { test, expect, login } from './fixtures'
import { compareVersions } from '../src/app/version/config'

test('release data matches the deployed notification and acknowledgment', {
  annotation: { type: 'shard_isolation', description: 'independent' },
}, async ({ page, owned }) => {
  const expected = JSON.parse(readFileSync('public/static/release.json', 'utf8'))
  const versionUpdates = expected as Array<{ version: string; title: string }>
  const currentVersion = versionUpdates.map(entry => entry.version).sort(compareVersions).at(-1)!
  const previous = versionUpdates.map(entry => entry.version)
    .filter(version => compareVersions(version, currentVersion) < 0)
    .sort(compareVersions).at(-1) ?? '0.0.0'
  const response = await page.request.get('/static/release.json')
  expect(response.ok()).toBe(true)
  expect(await response.json()).toEqual(expected)
  await page.addInitScript(version => {
    if (!localStorage.getItem('release-smoke-initialized')) {
      localStorage.setItem('mc-admin-last-seen-version', version)
      localStorage.setItem('release-smoke-initialized', 'true')
    }
  }, previous)
  await login(page, owned)
  const dialog = page.getByRole('dialog').filter({ hasText: '版本更新通知' })
  await expect(dialog).toBeVisible()
  await expect(dialog).toContainText(`欢迎使用 MC Admin v${currentVersion}！`)
  const latest = versionUpdates.find(entry => entry.version === currentVersion)!
  await expect(dialog.getByRole('heading', { level: 5 })).toHaveText(latest.title)
  await dialog.getByRole('button', { name: '明白了', exact: true }).click()
  await expect(dialog).toBeHidden()
  expect(await page.evaluate(() => localStorage.getItem('mc-admin-last-seen-version'))).toBe(currentVersion)
  await page.reload()
  await expect(page.getByRole('button', { name: '退出登录', exact: true })).toBeVisible()
  await page.waitForTimeout(1200)
  await expect(dialog).toBeHidden()
})
