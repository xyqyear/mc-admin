// Pure-function coordinate conversions for the server map.
//
// Minecraft world space is measured in *blocks*. A *chunk* is 16 x 16 blocks.
// A *region* is 32 x 32 chunks = 512 x 512 blocks. mcmap renders one PNG per
// region at 512 px wide (1 block = 1 px). We use Leaflet's CRS.Simple with a
// tile size of 512 so leaflet's tile coordinates map 1:1 to region coordinates.
//
// In Leaflet's grid coordinates, y grows downward — which matches Minecraft's
// z axis directly, so leaflet (x, y) == region (x, z).

export const BLOCKS_PER_CHUNK = 16
export const CHUNKS_PER_REGION = 32
export const BLOCKS_PER_REGION = BLOCKS_PER_CHUNK * CHUNKS_PER_REGION // 512

export interface ChunkCoord {
  cx: number
  cz: number
}

export interface RegionCoord {
  rx: number
  rz: number
}

export interface BlockCoord {
  bx: number
  bz: number
}

const floorDiv = (a: number, b: number): number => Math.floor(a / b)

export function blockToChunk(b: BlockCoord): ChunkCoord {
  return {
    cx: floorDiv(b.bx, BLOCKS_PER_CHUNK),
    cz: floorDiv(b.bz, BLOCKS_PER_CHUNK),
  }
}

export function blockToRegion(b: BlockCoord): RegionCoord {
  return {
    rx: floorDiv(b.bx, BLOCKS_PER_REGION),
    rz: floorDiv(b.bz, BLOCKS_PER_REGION),
  }
}

export function chunkToRegion(c: ChunkCoord): RegionCoord {
  return {
    rx: floorDiv(c.cx, CHUNKS_PER_REGION),
    rz: floorDiv(c.cz, CHUNKS_PER_REGION),
  }
}

export function chunkToBlock(c: ChunkCoord): BlockCoord {
  return {
    bx: c.cx * BLOCKS_PER_CHUNK,
    bz: c.cz * BLOCKS_PER_CHUNK,
  }
}

export function regionToBlock(r: RegionCoord): BlockCoord {
  return {
    bx: r.rx * BLOCKS_PER_REGION,
    bz: r.rz * BLOCKS_PER_REGION,
  }
}

export function chunkKey(c: ChunkCoord): `${number},${number}` {
  return `${c.cx},${c.cz}`
}

export function chunkKeyToCoord(k: `${number},${number}`): ChunkCoord {
  const [cx, cz] = k.split(',').map(Number)
  return { cx, cz }
}

// Iterate all chunks within a block-aligned bounding box (inclusive).
export function* chunksInBlockBox(
  min: BlockCoord,
  max: BlockCoord
): IterableIterator<ChunkCoord> {
  const minC = blockToChunk(min)
  const maxC = blockToChunk(max)
  for (let cz = minC.cz; cz <= maxC.cz; cz++) {
    for (let cx = minC.cx; cx <= maxC.cx; cx++) {
      yield { cx, cz }
    }
  }
}
