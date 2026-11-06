const cleanups = new Set<() => void>()

export function clearUploadAnimations() {
  for (const cleanup of cleanups) cleanup()
}

export function animateUploadMinimize(source: HTMLElement | null) {
  const target = document.querySelector<HTMLElement>('[data-task-center-launcher]')
  if (!source || !target || typeof source.animate !== 'function' || window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) return
  const from = source.getBoundingClientRect()
  const to = target.getBoundingClientRect()
  if (!from.width || !from.height || !to.width || !to.height) return
  const copy = source.cloneNode(true) as HTMLElement
  copy.removeAttribute('id')
  copy.removeAttribute('role')
  copy.removeAttribute('aria-labelledby')
  copy.removeAttribute('aria-describedby')
  copy.setAttribute('aria-hidden', 'true')
  copy.setAttribute('data-upload-minimize', '')
  copy.inert = true
  for (const element of copy.querySelectorAll('[id]')) element.removeAttribute('id')
  Object.assign(copy.style, {
    position: 'fixed', top: `${from.top}px`, left: `${from.left}px`, width: `${from.width}px`, height: `${from.height}px`,
    maxWidth: 'none', maxHeight: 'none', margin: '0', translate: 'none', transform: 'none', transformOrigin: 'top left',
    pointerEvents: 'none', overflow: 'hidden', zIndex: '100', animation: 'none', transition: 'none',
  })
  document.body.appendChild(copy)
  let animation: Animation | undefined
  let disposed = false
  const cleanup = () => {
    if (disposed) return
    disposed = true
    clearTimeout(timer)
    animation?.cancel()
    copy.remove()
    cleanups.delete(cleanup)
  }
  const timer = window.setTimeout(cleanup, 600)
  cleanups.add(cleanup)
  try {
    animation = copy.animate([
      { transform: 'translate(0, 0) scale(1)', opacity: 1 },
      { transform: `translate(${to.left - from.left}px, ${to.top - from.top}px) scale(${to.width / from.width}, ${to.height / from.height})`, opacity: 0.15 },
    ], { duration: 360, easing: 'cubic-bezier(0.4, 0, 0.2, 1)', fill: 'forwards' })
    void animation.finished.then(cleanup, cleanup)
  } catch {
    cleanup()
  }
}
