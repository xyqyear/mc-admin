import type {
  DimensionInfoResponse,
  WorldLayoutResponse,
  WorldRootResponse,
} from '@/types/WorldRestore'

export interface CurrentWorldDimension {
  rootList: WorldRootResponse[]
  currentDimension: DimensionInfoResponse | null
  currentRoot: WorldRootResponse | null
}

export interface DimensionOption {
  value: string
  label: string
}

export function relpathOf(regionDir: string, worldRootPath: string): string {
  const sep = '/'
  const rootBase = worldRootPath.split(sep).pop() ?? ''
  if (!rootBase) return regionDir
  const idx = regionDir.lastIndexOf(`${sep}${rootBase}${sep}`)
  if (idx < 0) {
    return `${rootBase}/${regionDir.split(sep).pop() ?? ''}`
  }
  return regionDir.slice(idx + 1)
}

export function dimensionPathOf(
  regionDir: string,
  worldRootPath: string,
): string {
  const region = regionDir.replace(/\/+$/, '')
  const root = worldRootPath.replace(/\/+$/, '')
  const suffix = '/region'
  const dimensionDir = region.endsWith(suffix)
    ? region.slice(0, -suffix.length)
    : region
  if (dimensionDir === root) return '.'
  const prefix = `${root}/`
  if (dimensionDir.startsWith(prefix)) return dimensionDir.slice(prefix.length)
  return dimensionDir.split('/').pop() ?? dimensionDir
}

export function labelForDimension(
  regionDir: string,
  worldRootPath: string,
  labels: Record<string, string> | undefined,
): string {
  const dimensionPath = dimensionPathOf(regionDir, worldRootPath)
  return labels?.[dimensionPath] ?? dimensionPath.replace(/^dimensions\//, '')
}

export function selectWorldDimension(
  layout: WorldLayoutResponse | undefined,
  dimensionRelpath: string | null,
): CurrentWorldDimension {
  const roots = layout?.world_roots ?? []
  if (roots.length === 0) {
    return { rootList: [], currentDimension: null, currentRoot: null }
  }
  if (dimensionRelpath) {
    for (const root of roots) {
      const match = root.dimensions.find(
        (d) => relpathOf(d.region_dir, root.path) === dimensionRelpath,
      )
      if (match) {
        return {
          rootList: roots,
          currentDimension: match,
          currentRoot: root,
        }
      }
    }
  }
  const root = roots[0]
  const dim =
    root.dimensions.find((d) => dimensionPathOf(d.region_dir, root.path) === '.') ??
    root.dimensions[0] ??
    null
  return { rootList: roots, currentDimension: dim, currentRoot: root }
}

export function buildDimensionOptions(
  layout: WorldLayoutResponse | undefined,
  labels: Record<string, string> | undefined,
): DimensionOption[] {
  if (!layout) return []
  const multipleRoots = layout.world_roots.length > 1
  const out: DimensionOption[] = []
  for (const root of layout.world_roots) {
    for (const dim of root.dimensions) {
      const rel = relpathOf(dim.region_dir, root.path)
      const dimLabel = labelForDimension(dim.region_dir, root.path, labels)
      const label = multipleRoots ? `${root.name} / ${dimLabel}` : dimLabel
      out.push({ value: rel, label })
    }
  }
  return out
}
