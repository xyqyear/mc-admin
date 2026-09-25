export type Vertex = readonly [number, number]
export type Ring = Vertex[]

type ChunkKey = `${number},${number}`

const vk = (x: number, z: number): string => `${x},${z}`

function popList<V>(map: Map<string, V[]>, key: string): V | undefined {
  const list = map.get(key)
  if (!list || list.length === 0) return undefined
  const v = list.shift()!
  if (list.length === 0) map.delete(key)
  return v
}

export function computeBoundaryRings(chunks: Iterable<[number, number]>): Ring[] {
  const inCluster = new Set<ChunkKey>()
  for (const [cx, cz] of chunks) {
    inCluster.add(`${cx},${cz}`)
  }
  const has = (cx: number, cz: number) =>
    inCluster.has(`${cx},${cz}` as ChunkKey)

  // Cluster-on-left boundary edges; popped as walked so each edge traverses once.
  const adj = new Map<string, Vertex[]>()
  const pushEdge = (a: Vertex, b: Vertex) => {
    const key = vk(a[0], a[1])
    const list = adj.get(key) ?? []
    list.push(b)
    adj.set(key, list)
  }

  for (const key of inCluster) {
    const [cxStr, czStr] = key.split(',')
    const cx = Number(cxStr)
    const cz = Number(czStr)
    // Top edge: neighbor north (cz - 1) missing → walk east → west, cluster south.
    if (!has(cx, cz - 1)) pushEdge([cx + 1, cz], [cx, cz])
    // Bottom edge: neighbor south missing → walk west → east, cluster north.
    if (!has(cx, cz + 1)) pushEdge([cx, cz + 1], [cx + 1, cz + 1])
    // Left edge: neighbor west missing → walk north → south, cluster east.
    if (!has(cx - 1, cz)) pushEdge([cx, cz], [cx, cz + 1])
    // Right edge: neighbor east missing → walk south → north, cluster west.
    if (!has(cx + 1, cz)) pushEdge([cx + 1, cz + 1], [cx + 1, cz])
  }

  const rings: Ring[] = []
  while (adj.size > 0) {
    const startKey = adj.keys().next().value as string
    const [sx, sz] = startKey.split(',').map(Number)
    const ring: Vertex[] = [[sx, sz]]
    let cursor = popList(adj, startKey)
    if (!cursor) {
      adj.delete(startKey)
      continue
    }
    while (vk(cursor[0], cursor[1]) !== startKey) {
      ring.push(cursor)
      const cKey = vk(cursor[0], cursor[1])
      const next = popList(adj, cKey)
      if (!next) {
        // Should not happen for closed boundaries; bail to avoid an infinite loop.
        break
      }
      cursor = next
    }
    if (ring.length >= 3) rings.push(simplifyCollinear(ring))
  }
  return rings
}

function simplifyCollinear(ring: Ring): Ring {
  if (ring.length < 3) return ring
  const out: Vertex[] = []
  const n = ring.length
  for (let i = 0; i < n; i++) {
    const prev = ring[(i - 1 + n) % n]
    const cur = ring[i]
    const next = ring[(i + 1) % n]
    const dx1 = cur[0] - prev[0]
    const dz1 = cur[1] - prev[1]
    const dx2 = next[0] - cur[0]
    const dz2 = next[1] - cur[1]
    // Collinear if cross product == 0 AND same direction (not a 180° doubleback).
    if (dx1 * dz2 - dz1 * dx2 === 0 && dx1 * dx2 + dz1 * dz2 > 0) continue
    out.push(cur)
  }
  return out
}
