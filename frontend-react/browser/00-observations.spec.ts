import { test, expect, login } from './fixtures'
import { createHash } from 'node:crypto'
import { readFile } from 'node:fs/promises'
import path from 'node:path'

test('overview polling and cold/warm map requests @observations', async ({ page, api, owned, observation }) => {
  await api.stopped()
  await api.initializeMap()
  const regions = await api.json<Array<[number, number, number]>>(api.server('/map/regions?region=world%2Fregion'))
  observation.describe({
    client_source: api.clientSource ?? 'Existing application cache or normal application download',
    region_count: regions.length,
    regions: await Promise.all(regions.map(async ([x, z]) => ({ x, z, sha256: createHash('sha256').update(await readFile(path.join(owned.server_path, 'data/world/region', `r.${x}.${z}.mca`))).digest('hex') }))),
    view: { dimension: 'world/region', cx: 0, cz: 0, z: 0 },
    workload: 'Stopped, freshly generated flat world. Record geometry and hashes because the fixture does not fix Minecraft world seed.',
  })
  await login(page, owned)
  await observation.measure('overview-15s', async () => {
    await page.goto('/overview')
    await expect(page.getByRole('row').filter({ hasText: owned.server_id })).toBeVisible()
    await page.waitForTimeout(15_000)
  })
  await observation.measure('detail-after-overview', async () => {
    await page.getByRole('row').filter({ hasText: owned.server_id }).getByTitle('服务器详情', { exact: true }).click()
    await expect(page.getByRole('button', { name: /启动/ }).first()).toBeVisible()
    await page.waitForTimeout(5_000)
  })
  const route = `/server/${owned.server_id}/world-restore#dim=world%2Fregion&cx=0&cz=0&z=0`
  await observation.measure('map-first-view', async () => {
    await page.goto(route)
    await expect(page.locator('.leaflet-container')).toBeVisible()
    await expect.poll(async () => page.locator('img.leaflet-tile').evaluateAll(images => images.filter(image => (image as HTMLImageElement).naturalWidth > 0).length), { timeout: 120_000 }).toBeGreaterThan(0)
    await page.waitForTimeout(3_000)
  })
  await observation.measure('map-same-view-reload', async () => {
    await page.reload()
    await expect(page.locator('.leaflet-container')).toBeVisible()
    await expect.poll(async () => page.locator('img.leaflet-tile').evaluateAll(images => images.filter(image => (image as HTMLImageElement).naturalWidth > 0).length)).toBeGreaterThan(0)
    await page.waitForTimeout(3_000)
  })
  await observation.measure('map-idle-15s', async () => { await page.waitForTimeout(15_000) })
})
