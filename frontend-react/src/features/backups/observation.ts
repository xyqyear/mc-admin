import type { ActiveRestorations, SnapshotScope } from './contracts'

function isScope(value: unknown): value is SnapshotScope {
  if (!value || typeof value !== 'object') return false
  const scope = value as Record<string, unknown>
  if (scope.kind === 'global') return true
  if (typeof scope.server_id !== 'string' || !scope.server_id) return false
  if (scope.kind === 'server') return true
  if (scope.kind === 'paths') return Array.isArray(scope.paths) && scope.paths.every(path => typeof path === 'string')
  if (scope.kind !== 'world' || !scope.selection || typeof scope.selection !== 'object') return false
  const selection = scope.selection as Record<string, unknown>
  return ['world', 'dimension', 'regions', 'chunks'].includes(String(selection.type))
}

export function activeRestorationIndex(rows: unknown[] | undefined, serverId?: string): ActiveRestorations | undefined {
  if (!rows) return undefined
  const restorations: ActiveRestorations['restorations'] = []
  for (const value of rows) {
    if (!value || typeof value !== 'object') return undefined
    const row = value as Record<string, unknown>
    if (typeof row.id !== 'string' || typeof row.operation_id !== 'string'
      || !['pending', 'running'].includes(String(row.status)) || !isScope(row.scope)
      || !Array.isArray(row.targets) || !row.targets.every(target => target && typeof target === 'object'
        && typeof target.server_id === 'string' && typeof target.generation === 'number')) return undefined
    if (serverId && !('server_id' in row.scope && row.scope.server_id === serverId)
      && !row.targets.some(target => target.server_id === serverId)) continue
    restorations.push({ id: row.id, operation_id: row.operation_id, status: row.status as 'pending' | 'running', scope: row.scope })
  }
  return { restorations, total: restorations.length }
}
