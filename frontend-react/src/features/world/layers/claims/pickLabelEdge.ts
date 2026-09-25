export type LabelSide = 'top' | 'bottom'

export interface LabelEdge {
  side: LabelSide
  bx: number
  bz: number
  runLength: number
}

interface Run {
  cz: number
  startCx: number
  endCx: number // inclusive
}

function longestRunOnSide(
  chunks: Set<string>,
  side: LabelSide,
): Run | null {
  const rowMap = new Map<number, number[]>()
  for (const key of chunks) {
    const [cxStr, czStr] = key.split(',')
    const cx = Number(cxStr)
    const cz = Number(czStr)
    const row = rowMap.get(cz)
    if (row) row.push(cx)
    else rowMap.set(cz, [cx])
  }

  let best: Run | null = null
  for (const [cz, cxs] of rowMap) {
    cxs.sort((a, b) => a - b)
    const neighborCz = side === 'top' ? cz - 1 : cz + 1
    let runStart: number | null = null
    let prev: number | null = null
    const finalize = (endCx: number) => {
      if (runStart === null) return
      const len = endCx - runStart + 1
      if (!best || len > best.endCx - best.startCx + 1) {
        best = { cz, startCx: runStart, endCx }
      }
    }
    for (const cx of cxs) {
      const outward = !chunks.has(`${cx},${neighborCz}`)
      if (outward && (prev === null || cx === prev + 1)) {
        if (runStart === null) runStart = cx
      } else if (outward) {
        finalize(prev!)
        runStart = cx
      } else {
        finalize(prev ?? -Infinity)
        runStart = null
      }
      prev = cx
    }
    if (prev !== null && runStart !== null) finalize(prev)
  }
  return best
}

export function pickLabelEdge(
  chunks: Iterable<[number, number]>,
): LabelEdge | null {
  const set = new Set<string>()
  for (const [cx, cz] of chunks) set.add(`${cx},${cz}`)
  if (set.size === 0) return null
  const top = longestRunOnSide(set, 'top')
  const bottom = longestRunOnSide(set, 'bottom')
  let chosen: Run | null = top
  let side: LabelSide = 'top'
  if (bottom && (!top || bottom.endCx - bottom.startCx > top.endCx - top.startCx)) {
    chosen = bottom
    side = 'bottom'
  }
  if (!chosen) {
    // Ring-only cluster fallback: place at centroid.
    let sumX = 0
    let sumZ = 0
    for (const key of set) {
      const [cxStr, czStr] = key.split(',')
      sumX += Number(cxStr)
      sumZ += Number(czStr)
    }
    const n = set.size
    return {
      side: 'top',
      bx: (sumX / n) * 16 + 8,
      bz: (sumZ / n) * 16 + 8,
      runLength: 1,
    }
  }
  const midCxBlock = ((chosen.startCx + chosen.endCx + 1) / 2) * 16
  const edgeBz = side === 'top' ? chosen.cz * 16 : (chosen.cz + 1) * 16
  return {
    side,
    bx: midCxBlock,
    bz: edgeBz,
    runLength: chosen.endCx - chosen.startCx + 1,
  }
}
