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
  if (!roots.length || roots.some(path => ignored.some(root => within(path, root)))) {
    return { allowed: false, reason: '此范围已被快照规则忽略，不能创建快照或恢复', skipped_paths: [], skipped_count: 0 }
  }
  const skipped = ignored.filter(path => roots.some(root => within(path, root)))
  return { allowed: true, reason: null, skipped_paths: skipped.slice(0, 100), skipped_count: skipped.length }
}
