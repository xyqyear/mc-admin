// Stable per-team palette. Hashing the team id picks one of 14 hues so the
// same team paints the same color across reloads, dimensions, and devices.
// Red hues are intentionally absent so the force-loaded tint stays visually
// distinct on any team.

import type { FtbTeamType } from '@/types/FtbClaims'

const HUES = [
  40, 55, 70, 90, 110, 135, 160, 180, 200, 220, 245, 270, 295, 315,
] as const

function hashStringToInt(s: string): number {
  // FNV-1a 32-bit. We only need a uniform distribution over a small palette,
  // not cryptographic strength.
  let h = 0x811c9dc5
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i)
    h = Math.imul(h, 0x01000193)
  }
  return h >>> 0
}

export interface TeamColor {
  // Use for polygon fill (semi-transparent) and the side-panel accent strip.
  hue: number
  // CSS color strings precomputed for convenience.
  stroke: string
  fill: string
  fillStrong: string
  text: string
}

export function teamColors(teamId: string, type: FtbTeamType): TeamColor {
  if (type === 'server') {
    // Server-claim chunks: neutral gray so player teams stay distinguishable.
    return {
      hue: -1,
      stroke: 'hsl(220 6% 55%)',
      fill: 'hsla(220 6% 55% / 0.20)',
      fillStrong: 'hsla(220 6% 55% / 0.45)',
      text: 'hsl(220 8% 18%)',
    }
  }
  const hue = HUES[hashStringToInt(teamId) % HUES.length]
  // Saturation/lightness chosen to read both on the dark Leaflet card bg and
  // on light/dark map tiles.
  const sat = type === 'unknown' ? 25 : 70
  const lightness = 50
  const stroke = `hsl(${hue} ${sat}% ${lightness}%)`
  const fill = `hsla(${hue} ${sat}% ${lightness}% / 0.22)`
  const fillStrong = `hsla(${hue} ${sat}% ${lightness}% / 0.45)`
  const text = `hsl(${hue} ${sat + 10}% ${lightness - 28}%)`
  return { hue, stroke, fill, fillStrong, text }
}
