import { afterEach, expect, it, vi } from 'vitest'
import { animateUploadMinimize, clearUploadAnimations } from './minimize'

afterEach(() => { clearUploadAnimations(); document.body.replaceChildren(); vi.restoreAllMocks(); vi.unstubAllGlobals() })

function elements() {
  const source = document.createElement('div')
  source.innerHTML = '<button id="original-button">上传</button>'
  source.setAttribute('role', 'dialog')
  const target = document.createElement('button')
  target.dataset.taskCenterLauncher = ''
  document.body.append(source, target)
  vi.spyOn(source, 'getBoundingClientRect').mockReturnValue(DOMRect.fromRect({ x: 100, y: 80, width: 600, height: 400 }))
  vi.spyOn(target, 'getBoundingClientRect').mockReturnValue(DOMRect.fromRect({ x: 900, y: 650, width: 48, height: 48 }))
  return source
}

it('shrinks to the current launcher bounds and removes the inert visual copy after completion', async () => {
  const source = elements()
  let finish!: () => void
  const animation = { finished: new Promise<void>(resolve => { finish = resolve }), cancel: vi.fn() }
  const animate = vi.fn(() => animation)
  vi.stubGlobal('matchMedia', () => ({ matches: false }))
  Object.defineProperty(HTMLElement.prototype, 'animate', { configurable: true, value: animate })
  animateUploadMinimize(source)
  const copy = document.querySelector<HTMLElement>('[data-upload-minimize]')!
  expect(copy.getAttribute('aria-hidden')).toBe('true')
  expect(copy.inert).toBe(true)
  expect(copy.style.pointerEvents).toBe('none')
  expect(copy.querySelector('[id]')).toBeNull()
  expect(animate.mock.calls[0]).toEqual([
    [{ transform: 'translate(0, 0) scale(1)', opacity: 1 }, { transform: 'translate(800px, 570px) scale(0.08, 0.12)', opacity: 0.15 }],
    { duration: 360, easing: 'cubic-bezier(0.4, 0, 0.2, 1)', fill: 'forwards' },
  ])
  finish()
  await animation.finished
  expect(document.querySelector('[data-upload-minimize]')).toBeNull()
  expect(source.isConnected).toBe(true)
  delete (HTMLElement.prototype as { animate?: unknown }).animate
})

it('honors reduced motion and skips animation without losing the source', () => {
  const source = elements()
  const animate = vi.fn()
  Object.defineProperty(source, 'animate', { value: animate })
  vi.stubGlobal('matchMedia', () => ({ matches: true }))
  animateUploadMinimize(source)
  expect(animate).not.toHaveBeenCalled()
  expect(document.querySelector('[data-upload-minimize]')).toBeNull()
  expect(source.isConnected).toBe(true)
})

it('cleans up when animation fails or the authenticated session ends', () => {
  const source = elements()
  Object.defineProperty(HTMLElement.prototype, 'animate', { configurable: true, value: () => { throw new Error('unavailable') } })
  animateUploadMinimize(source)
  expect(document.querySelector('[data-upload-minimize]')).toBeNull()
  const cancel = vi.fn()
  Object.defineProperty(HTMLElement.prototype, 'animate', { configurable: true, value: () => ({ finished: new Promise(() => {}), cancel }) })
  animateUploadMinimize(source)
  clearUploadAnimations()
  expect(document.querySelector('[data-upload-minimize]')).toBeNull()
  expect(cancel).toHaveBeenCalledTimes(1)
  delete (HTMLElement.prototype as { animate?: unknown }).animate
})
