import type { Page } from '@playwright/test'
import { test, expect, login } from './fixtures'
import { withCleanup } from './cleanup'

const isolated = { annotation: { type: 'shard_isolation', description: 'independent' } }

async function inNewPage(source: Page, open: () => Promise<void>, check: (page: Page) => Promise<void>) {
  const [opened] = await Promise.all([source.context().waitForEvent('page'), open()])
  try {
    await check(opened)
  } finally {
    await opened.close()
  }
}

test('native sidebar and styled links open new tabs without changing the source route', isolated, async ({ page, owned }) => {
  await login(page, owned)
  const filesPath = `/server/${owned.server_id}/files`
  await page.goto(filesPath)
  const files = page.locator('[data-sidebar="menu-sub-button"]').filter({ hasText: /^文件$/ })
  const selfCheck = page.locator('[data-sidebar="menu-button"]').filter({ hasText: /^系统自检$/ })
  await expect(files).toBeVisible()
  await expect(files).toHaveAttribute('data-active', '')
  await expect(selfCheck).not.toHaveAttribute('data-active')
  await expect(selfCheck).toHaveAttribute('href', '/')
  const sourceURL = page.url()
  const expanded = await page.locator('[data-sidebar="menu-sub"]').allTextContents()
  for (const open of [
    () => selfCheck.click({ button: 'middle' }),
    () => selfCheck.click({ modifiers: ['ControlOrMeta'] }),
  ]) {
    await inNewPage(page, open, async opened => {
      await expect(opened).toHaveURL(new URL('/', owned.base_url).href)
      await expect(opened.getByRole('button', { name: '退出登录', exact: true })).toBeVisible()
    })
    await expect(page).toHaveURL(sourceURL)
    await expect(files).toBeVisible()
    await expect(files).toHaveAttribute('data-active', '')
    await expect(selfCheck).not.toHaveAttribute('data-active')
    expect(await page.locator('[data-sidebar="menu-sub"]').allTextContents()).toEqual(expanded)
  }
  await selfCheck.click()
  await expect(page).toHaveURL(new URL('/', owned.base_url).href)
  await expect(selfCheck).toHaveAttribute('data-active', '')
  await page.goto('/overview')
  const overviewURL = page.url()
  await inNewPage(page, () => page.getByRole('link', { name: '服务器详情', exact: true }).click({ button: 'middle' }), async opened => {
    await expect(opened).toHaveURL(new URL(`/server/${owned.server_id}`, owned.base_url).href)
    await expect(opened.getByRole('button', { name: '退出登录', exact: true })).toBeVisible()
  })
  await expect(page).toHaveURL(overviewURL)
})

test('native search links preserve captured destinations selection drafts and expansion', isolated, async ({ page, api, owned }) => {
  const root = `browser-native-links-${Date.now().toString(36)}`
  const fileName = '设置 a+b #&[1].txt'
  const route = `/server/${owned.server_id}/files`
  let created = false
  await withCleanup(async () => {
    await api.stopped()
    await api.json(api.server('/files/create'), 'POST', { path: '/', name: root, type: 'directory' })
    created = true
    for (const [folder, name] of [['nested', fileName], ['other', 'other.txt']]) {
      await api.json(api.server('/files/create'), 'POST', { path: '/' + root, name: folder, type: 'directory' })
      await api.json(api.server('/files/create'), 'POST', { path: `/${root}/${folder}`, name, type: 'file' })
      await api.writeFile(`${root}/${folder}/${name}`, 'native link source bytes\n')
    }
    await login(page, owned)
    await page.goto(`${route}?path=${encodeURIComponent('/' + root)}`)
    const sourceURL = page.url()
    await page.getByRole('button', { name: '高级搜索', exact: true }).click()
    const search = page.getByRole('dialog', { name: '高级搜索', exact: true })
    const pattern = search.getByLabel('搜索模式', { exact: true })
    await pattern.fill('[.]txt$')
    await search.getByRole('button', { name: '搜索', exact: true }).click()
    const result = search.getByRole('link', { name: fileName, exact: true })
    await expect(result).toBeVisible()
    const selected = search.getByRole('checkbox', { name: `选择搜索结果 /nested/${fileName}`, exact: true })
    await selected.click()
    await expect(selected).toBeChecked()
    await search.getByRole('button', { name: '收起 /other', exact: true }).click()
    await pattern.fill('unsubmitted draft')
    const icon = search.getByRole('link', { name: `在新标签页打开 /nested/${fileName}`, exact: true })
    await expect(icon).toHaveAttribute('target', '_blank')
    await expect(icon).toHaveAttribute('rel', 'noopener noreferrer')
    for (const [open, isolatedOpener] of [
      [() => result.click({ button: 'middle' }), false],
      [() => result.click({ modifiers: ['ControlOrMeta'] }), false],
      [() => icon.click(), true],
    ] as const) {
      await inNewPage(page, open, async opened => {
        await expect(opened).toHaveURL(url => url.pathname === route
          && url.searchParams.get('path') === `/${root}/nested`
          && url.searchParams.get('q') === fileName
          && url.searchParams.get('regex') !== 'true')
        await expect(opened.getByText(fileName, { exact: true }).first()).toBeVisible()
        if (isolatedOpener) expect(await opened.evaluate(() => window.opener === null)).toBe(true)
      })
      await expect(page).toHaveURL(sourceURL)
      await expect(search).toBeVisible()
      await expect(selected).toBeChecked()
      await expect(pattern).toHaveValue('unsubmitted draft')
      await expect(search.getByRole('button', { name: '展开 /other', exact: true })).toBeVisible()
    }
    const parent = search.getByRole('link', { name: 'nested', exact: true })
    await inNewPage(page, () => parent.click({ button: 'middle' }), async opened => {
      await expect(opened).toHaveURL(url => url.pathname === route
        && url.searchParams.get('path') === `/${root}/nested`
        && url.searchParams.get('q') === '[.]txt$'
        && url.searchParams.get('regex') === 'true')
      await expect(opened.getByText(fileName, { exact: true }).first()).toBeVisible()
    })
    await expect(selected).toBeChecked()
    await result.click()
    await expect(search).toBeHidden()
    await expect(page).toHaveURL(url => url.pathname === route
      && url.searchParams.get('path') === `/${root}/nested`
      && url.searchParams.get('q') === fileName
      && url.searchParams.get('regex') !== 'true')
    const fileURL = page.url()
    await page.goBack()
    await expect(page).toHaveURL(sourceURL)
    await page.goForward()
    await expect(page).toHaveURL(fileURL)
    const fileSelection = page.getByRole('checkbox', { name: `选择 /${root}/nested/${fileName}`, exact: true })
    await fileSelection.click()
    const breadcrumb = page.getByRole('navigation', { name: 'breadcrumb', exact: true })
    const ancestor = breadcrumb.getByRole('link', { name: root, exact: true })
    const up = page.getByRole('link', { name: '返回上级', exact: true })
    for (const open of [
      () => ancestor.click({ button: 'middle' }),
      () => up.click({ modifiers: ['ControlOrMeta'] }),
    ]) {
      await inNewPage(page, open, async opened => {
        await expect(opened).toHaveURL(url => url.pathname === route
          && url.searchParams.get('path') === `/${root}`
          && !url.searchParams.has('q') && !url.searchParams.has('regex'))
        await expect(opened.getByText('nested', { exact: true }).first()).toBeVisible()
      })
      await expect(page).toHaveURL(fileURL)
      await expect(fileSelection).toBeChecked()
    }
    await up.click()
    await expect(page).toHaveURL(sourceURL)
    await expect(page.getByRole('toolbar', { name: '所选文件操作', exact: true })).toBeHidden()
    const directorySelection = page.getByRole('checkbox', { name: `选择 /${root}/nested`, exact: true })
    await directorySelection.click()
    const directory = page.getByRole('link', { name: 'nested', exact: true })
    await inNewPage(page, () => directory.click({ button: 'middle' }), async opened => {
      await expect(opened).toHaveURL(url => url.pathname === route
        && url.searchParams.get('path') === `/${root}/nested`
        && !url.searchParams.has('q') && !url.searchParams.has('regex'))
      await expect(opened.getByText(fileName, { exact: true }).first()).toBeVisible()
    })
    await expect(page).toHaveURL(sourceURL)
    await expect(directorySelection).toBeChecked()
    await directory.click()
    await expect(page).toHaveURL(url => url.pathname === route
      && url.searchParams.get('path') === `/${root}/nested`
      && !url.searchParams.has('q') && !url.searchParams.has('regex'))
    await expect(page.getByRole('toolbar', { name: '所选文件操作', exact: true })).toBeHidden()
    expect((await api.file(`${root}/nested/${fileName}`)).content).toBe('native link source bytes\n')
  }, { label: 'navigation source files', run: async () => { if (created) await api.deleteFile(root) } })
})
