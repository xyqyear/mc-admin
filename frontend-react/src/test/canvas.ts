import { vi } from 'vitest'

export function mockCanvas() {
  const contexts = new WeakMap<HTMLCanvasElement, ReturnType<typeof createContext>>()
  function createContext() {
    const draws: { source: CanvasImageSource; x: number; y: number; alpha: number }[] = []
    const context = {
      globalAlpha: 1,
      draws,
      drawImage: vi.fn((source: CanvasImageSource, x: number, y: number) => {
        draws.push({ source, x, y, alpha: context.globalAlpha })
      }),
      clearRect: vi.fn(() => { draws.length = 0 }),
      fillText: vi.fn(), measureText: vi.fn((text: string) => ({ width: Array.from(text).length * 6 })),
      setTransform: vi.fn(), scale: vi.fn(), translate: vi.fn(), fillRect: vi.fn(), beginPath: vi.fn(),
      roundRect: vi.fn(), fill: vi.fn(), save: vi.fn(), clip: vi.fn(), restore: vi.fn(), stroke: vi.fn(), arc: vi.fn(),
    }
    return context
  }
  const contextFor = (canvas: HTMLCanvasElement) => {
    let context = contexts.get(canvas)
    if (!context) { context = createContext(); contexts.set(canvas, context) }
    return context
  }
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockImplementation(function (this: HTMLCanvasElement) {
    return contextFor(this) as unknown as CanvasRenderingContext2D
  })
  return contextFor
}
