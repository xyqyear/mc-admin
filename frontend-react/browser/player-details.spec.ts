import { appendFile, readFile, writeFile } from 'node:fs/promises'
import path from 'node:path'
import { test, expect, login } from './fixtures'
import { withCleanup } from './cleanup'

test('overview player cards open details by keyboard and retain the dialog after logout', { annotation: { type: 'shard_isolation', description: 'independent' } }, async ({ page, api, owned }) => {
  await api.running()
  const name = 'BrowserCardPlayer'
  const uuid = 'a18c0318-c079-4b44-a334-86a34ab4a503'
  const cachePath = path.join(owned.server_path, 'data', 'usercache.json')
  const logPath = path.join(owned.server_path, 'data', 'logs', 'latest.log')
  const cacheBytes = await readFile(cachePath)
  const cache = JSON.parse(cacheBytes.toString()) as Array<{ name: string; uuid: string }>
  const config = await api.json<{ config_data: Record<string, unknown> }>('/api/config/modules/players')
  await withCleanup(async () => {
    await writeFile(cachePath, JSON.stringify([...cache.filter(item => item.name !== name), { name, uuid }]))
    await expect.poll(async () => {
      await appendFile(logPath, `\n[12:00:00] [Server thread/INFO]: UUID of player ${name} is ${uuid}\n`)
      return (await api.response('/api/players/uuid/' + uuid.replaceAll('-', ''))).status
    }).toBe(200)
    await login(page, owned)
    await page.goto(`/server/${owned.server_id}`)
    await appendFile(logPath, `[12:00:01] [Server thread/INFO]: ${name}[/127.0.0.1:42] logged in with entity id 2\n`)
    await expect.poll(async () => (await api.json<Array<{ uuid: string }>>(api.server('/online-players'))).some(player => player.uuid === uuid.replaceAll('-', ''))).toBe(true)
    // Observing reconciliation gives the injected session a stable RCON interval for UI assertions.
    await api.json('/api/config/modules/players', 'PUT', { config_data: { ...config.config_data, rcon_validation: { ...(config.config_data.rcon_validation as Record<string, unknown>), validation_interval_seconds: 3600 } } })
    await expect.poll(async () => (await api.json<Array<{ uuid: string }>>(api.server('/online-players'))).some(player => player.uuid === uuid.replaceAll('-', '')), { timeout: 90_000 }).toBe(false)
    await appendFile(logPath, `[12:00:02] [Server thread/INFO]: ${name}[/127.0.0.1:42] logged in with entity id 3\n`)
    await expect.poll(async () => (await api.json<Array<{ uuid: string }>>(api.server('/online-players'))).some(player => player.uuid === uuid.replaceAll('-', ''))).toBe(true)
    const card = page.getByRole('button', { name: `查看 ${name} 的玩家详情`, exact: true })
    await card.focus()
    await page.keyboard.press('Enter')
    const dialog = page.getByRole('dialog', { name: /玩家详情/ })
    await expect(dialog.getByText(name, { exact: true })).toBeVisible()
    await expect(page).toHaveURL(new RegExp(`/server/${owned.server_id}$`))
    await appendFile(logPath, `[12:00:02] [Server thread/INFO]: ${name} lost connection: Disconnected\n`)
    await expect(card).toBeHidden({ timeout: 30_000 })
    await expect(dialog).toBeVisible()
    await page.keyboard.press('Escape')
    await expect(dialog).toBeHidden()
    await expect(page).toHaveURL(new RegExp(`/server/${owned.server_id}$`))
  },
  { label: 'player logout', run: async () => {
    await appendFile(logPath, `[12:00:03] [Server thread/INFO]: ${name} lost connection: Disconnected\n`)
    await expect.poll(async () => (await api.json<Array<{ uuid: string }>>(api.server('/online-players'))).some(player => player.uuid === uuid.replaceAll('-', ''))).toBe(false)
  } },
  { label: 'player cache', run: () => writeFile(cachePath, cacheBytes) },
  { label: 'owned player record', run: async () => {
    await api.json('/api/config/modules/players', 'PUT', { config_data: { ...config.config_data, ignored_name_prefixes: [name] } })
    await api.json('/api/players/cleanup/ignored_name_prefix', 'DELETE')
  } },
  { label: 'player configuration', run: async () => { await api.json('/api/config/modules/players', 'PUT', config) } })
})
