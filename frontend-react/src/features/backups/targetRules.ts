import type { SnapshotTargetCheck } from './contracts'

function normalizedPath(path: string) {
  return path.split('/').filter(part => part && part !== '.').join('/')
}

function within(path: string, root: string) {
  return !root || path === root || path.startsWith(root + '/')
}

export function checkLogicalSnapshotPaths(paths: readonly string[], ignoredPaths: readonly string[]): SnapshotTargetCheck {
  const selected = [...new Set(paths.map(normalizedPath))].sort()
  const roots = selected.filter((path, index) => !selected.slice(0, index).some(root => within(path, root)))
  const ignored = [...new Set(ignoredPaths.map(normalizedPath))].sort()
  const allowed = roots.filter(path => !ignored.some(root => within(path, root)))
  const skipped = ignored.filter(path => roots.some(root => within(path, root) || within(root, path)))
  return {
    allowed: allowed.length > 0,
    reason: allowed.length ? null : '所选范围均被快照规则忽略，没有可处理的内容',
    skipped_paths: skipped.slice(0, 100),
    skipped_count: skipped.length,
  }
}
