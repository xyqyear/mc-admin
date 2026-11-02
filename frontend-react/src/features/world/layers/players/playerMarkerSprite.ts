import L from 'leaflet'

export const MARKER_SIZE = L.point(124, 45)
export const MARKER_ANCHOR = L.point(62, 29)
export type PlayerOnlineStatus = 'online' | 'offline' | 'unknown'

export function createPlayerMarkerSprite(
  label: string,
  status: PlayerOnlineStatus,
  avatar: HTMLImageElement | null,
  ratio: number,
  fontFamily: string,
): HTMLCanvasElement {
  const canvas = document.createElement('canvas')
  canvas.width = Math.ceil(MARKER_SIZE.x * ratio)
  canvas.height = Math.ceil(MARKER_SIZE.y * ratio)
  const context = canvas.getContext('2d')!
  context.scale(ratio, ratio)
  context.translate(2, 2)
  context.font = `600 10px ${fontFamily}`
  context.textAlign = 'center'
  context.textBaseline = 'middle'
  let name = label
  if (context.measureText(name).width > 112) {
    const characters = Array.from(label)
    let low = 0
    let high = characters.length
    while (low < high) {
      const middle = Math.ceil((low + high) / 2)
      if (context.measureText(characters.slice(0, middle).join('') + '…').width <= 112) low = middle
      else high = middle - 1
    }
    name = characters.slice(0, low).join('') + '…'
  }
  const nameWidth = Math.min(120, Math.ceil(context.measureText(name).width) + 8)
  context.fillStyle = 'rgba(15, 23, 42, 0.42)'
  context.fillRect(60 - nameWidth / 2, 0, nameWidth, 14)
  context.fillStyle = 'rgba(255, 255, 255, 0.9)'
  context.shadowColor = 'rgba(0, 0, 0, 0.5)'
  context.shadowBlur = 2
  context.shadowOffsetY = 1
  context.fillText(name, 60, 7)
  context.beginPath()
  context.roundRect(48.5, 15.5, 23, 23, 3.5)
  context.fillStyle = 'rgba(17, 24, 39, 0.55)'
  context.fill()
  context.shadowBlur = context.shadowOffsetY = 0
  context.shadowColor = 'transparent'
  if (avatar) {
    context.save()
    context.beginPath()
    context.roundRect(49, 16, 22, 22, 3)
    context.clip()
    context.imageSmoothingEnabled = false
    context.drawImage(avatar, 49, 16, 22, 22)
    context.restore()
  } else {
    context.fillStyle = 'rgba(255, 255, 255, 0.78)'
    context.font = `700 11px ${fontFamily}`
    context.fillText(Array.from(label)[0]?.toUpperCase() || '?', 60, 27)
  }
  context.beginPath()
  context.roundRect(48.5, 15.5, 23, 23, 3.5)
  context.strokeStyle = 'rgba(255, 255, 255, 0.72)'
  context.lineWidth = 1
  context.stroke()
  if (status !== 'unknown') {
    context.beginPath()
    context.arc(70.5, 37.5, 3, 0, Math.PI * 2)
    context.fillStyle = status === 'online' ? 'rgb(34, 197, 94)' : 'rgba(148, 163, 184, 0.82)'
    context.fill()
    context.strokeStyle = 'rgba(15, 23, 42, 0.9)'
    context.stroke()
  }
  return canvas
}
