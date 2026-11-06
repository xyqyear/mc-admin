import { createHash } from 'node:crypto'
import { test, expect, login } from './fixtures'
import { withCleanup } from './cleanup'

for (const [kind, reducedMotion] of [['files', false], ['archive', false], ['archive', true]] as const) {
  test(`${kind} upload survives dismissal and navigation and reopens its real result${reducedMotion ? ' with reduced motion' : ''}`, { annotation: { type: 'shard_isolation', description: 'independent' } }, async ({ page, api, owned }) => {
    const name = `browser-upload-${kind}-${Date.now().toString(36)}.${kind === 'files' ? 'txt' : 'zip'}`
    const bytes = kind === 'files' ? Buffer.from('independent uploaded file bytes\n') : Buffer.from('504b0506000000000000000000000000000000000000', 'hex')
    let release!: () => void
    const released = new Promise<void>(resolve => { release = resolve })
    let held!: () => void
    const responseHeld = new Promise<void>(resolve => { held = resolve })
    let submissions = 0
    let delivered!: () => void
    const responseDelivered = new Promise<void>(resolve => { delivered = resolve })
    let publicationId = ''
    const pattern = kind === 'files' ? '**/api/servers/*/files/upload/multiple*' : '**/api/archive/upload/*/verify'
    await page.emulateMedia({ reducedMotion: reducedMotion ? 'reduce' : 'no-preference' })
    await page.route(pattern, async route => {
      submissions++
      const response = await route.fetch()
      expect(response.status()).toBe(kind === 'files' ? 200 : 202)
      if (kind === 'archive') publicationId = ((await response.json()) as { task_id: string }).task_id
      held()
      await released
      try { await route.fulfill({ response }) } finally { delivered() }
    })
    await withCleanup(async () => {
      await login(page, owned)
      await page.goto(kind === 'files' ? `/server/${owned.server_id}/files` : '/archives')
      const launcher = page.getByRole('button', { name: '任务中心', exact: true })
      await expect(launcher).toBeVisible()
      const before = await launcher.boundingBox()
      if (!before) throw new Error('Task-center launcher must have bounds')
      await page.mouse.move(before.x + 24, before.y + 24)
      await page.mouse.down()
      await page.mouse.move(before.x - 156, before.y - 76, { steps: 8 })
      await page.mouse.up()
      const target = await launcher.boundingBox()
      expect(target?.x).toBeLessThan(before.x)
      if (kind === 'files') {
        await expect(page.getByRole('button', { name: '上传文件', exact: true })).toBeVisible()
        await page.evaluate(({ name, content }) => {
          const transfer = new DataTransfer()
          transfer.items.add(new File([content], name, { type: 'text/plain' }))
          Object.defineProperty(transfer, 'items', { value: undefined })
          document.dispatchEvent(new DragEvent('drop', { bubbles: true, cancelable: true, dataTransfer: transfer }))
        }, { name, content: bytes.toString() })
      } else {
        await page.getByRole('button', { name: '上传文件', exact: true }).click()
        await page.getByRole('dialog', { name: '上传压缩包' }).locator('input[type=file]').setInputFiles({ name, mimeType: 'application/zip', buffer: bytes })
      }
      const dialog = page.getByRole('dialog', { name: kind === 'files' ? '上传文件和文件夹' : '上传压缩包', exact: true })
      await dialog.getByRole('button', { name: kind === 'files' ? '检查冲突并上传' : '开始上传', exact: true }).click()
      await responseHeld
      await page.evaluate(() => {
        const source = document.querySelector<HTMLElement>('[role="dialog"]')
        if (!source) throw new Error('Upload dialog must be visible before minimization')
        const observer = new MutationObserver(() => {
          const copy = document.querySelector<HTMLElement>('[data-upload-minimize]')
          if (!copy) return
          const frames = (copy.getAnimations()[0]?.effect as KeyframeEffect | null)?.getKeyframes()
          const matrix = new DOMMatrix(frames?.at(-1)?.transform as string)
          const geometry = {
            hidden: copy.getAttribute('aria-hidden'), inert: copy.inert,
            end: { x: parseFloat(copy.style.left) + matrix.e, y: parseFloat(copy.style.top) + matrix.f,
              width: parseFloat(copy.style.width) * matrix.a, height: parseFloat(copy.style.height) * matrix.d },
          }
          requestAnimationFrame(() => {
            const originalStyle = getComputedStyle(source)
            const copyStyle = getComputedStyle(copy)
            document.documentElement.dataset.uploadAnimation = JSON.stringify({
              ...geometry,
              originalVisible: source.isConnected && originalStyle.visibility !== 'hidden' && originalStyle.display !== 'none' && Number(originalStyle.opacity) > 0,
              copyVisible: copy.isConnected && copyStyle.visibility !== 'hidden' && copyStyle.display !== 'none' && Number(copyStyle.opacity) > 0,
            })
          })
          observer.disconnect()
        })
        observer.observe(document.body, { childList: true })
      })
      if (!target) throw new Error('Launcher must have bounds')
      if (kind === 'files') await page.mouse.click(20, 20)
      else await page.keyboard.press('Escape')
      await expect(dialog).toBeHidden()
      await expect(launcher).toBeFocused()
      await expect(page.getByText('上传窗口已收起，可在任务中心查看', { exact: true })).toBeVisible()
      if (!reducedMotion) {
        await expect(page.locator('html')).toHaveAttribute('data-upload-animation', /.+/)
        const evidence = JSON.parse((await page.locator('html').getAttribute('data-upload-animation')) || '{}')
        const landing = await launcher.boundingBox()
        if (!landing) throw new Error('Minimized upload must have a visible destination')
        expect(evidence.hidden).toBe('true')
        expect(evidence.inert).toBe(true)
        expect(evidence.originalVisible).toBe(false)
        expect(evidence.copyVisible).toBe(true)
        expect(evidence.end.x).toBeCloseTo(landing.x, 1)
        expect(evidence.end.y).toBeCloseTo(landing.y, 1)
        expect(evidence.end.width).toBeCloseTo(landing.width, 1)
        expect(evidence.end.height).toBeCloseTo(landing.height, 1)
        await expect(page.locator('[data-upload-minimize]')).toHaveCount(0)
      } else {
        expect(await page.locator('html').getAttribute('data-upload-animation')).toBeNull()
      }
      await page.getByRole('link', { name: '服务器总览', exact: true }).click()
      await expect(page).toHaveURL(/\/overview$/)
      await launcher.click()
      await expect(page.getByRole('tab', { name: /^上传/ })).toHaveAttribute('aria-selected', 'true')
      const uploads = page.getByRole('tabpanel', { name: /^上传/ })
      const heading = uploads.getByRole('button', { name: `查看上传：${name}`, exact: true })
      await expect(heading).toContainText(name)
      expect((await heading.innerText()).split(name)).toHaveLength(2)
      await expect(uploads.getByText(name, { exact: true })).toHaveCount(0)
      await expect(uploads.getByText('压缩包管理', { exact: true })).toHaveCount(0)
      if (kind === 'archive' && !reducedMotion) await uploads.screenshot({ path: test.info().outputPath('upload-task-center.png') })
      await heading.click()
      await expect(dialog).toBeVisible()
      expect(submissions).toBe(1)
      await dialog.getByRole('button', { name: '收起上传窗口', exact: true }).click()
      release()
      if (publicationId) await api.task(publicationId)
      await launcher.click()
      await expect(page.getByText('已结束 (1)', { exact: true })).toBeVisible()
      await page.getByRole('button', { name: `查看上传：${name}`, exact: true }).click()
      await expect(dialog.getByText(kind === 'files' ? '上传完成！' : '所有压缩包已上传并通过 SHA256 校验', { exact: true })).toBeVisible()
      const result = await api.response(kind === 'files' ? api.server(`/files/download?path=${encodeURIComponent(name)}`) : `/api/archive/download?path=${encodeURIComponent(name)}`)
      expect(result.status).toBe(200)
      expect(createHash('sha256').update(Buffer.from(await result.arrayBuffer())).digest('hex')).toBe(createHash('sha256').update(bytes).digest('hex'))
      expect(submissions).toBe(1)
      await dialog.getByRole('button', { name: '关闭', exact: true }).click()
      await launcher.click()
      await page.getByRole('button', { name: '清除已结束', exact: true }).click()
      await expect(page.getByText('暂无上传任务', { exact: true })).toBeVisible()
    },
    { label: 'upload response gate', run: async () => { release(); if (submissions) await responseDelivered; await page.unroute(pattern); if (publicationId) await api.task(publicationId, false) } },
    { label: 'uploaded bytes', run: async () => {
      const response = await api.response(kind === 'files' ? api.server(`/files?path=${encodeURIComponent(name)}`) : `/api/archive?path=${encodeURIComponent(name)}`, 'DELETE')
      if (response.status === 202) await api.task(((await response.json()) as { task_id: string }).task_id)
      else expect(response.status).toBe(404)
    } },
    )
  })
}
