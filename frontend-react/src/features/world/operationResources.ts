import type { QueryKey } from '@tanstack/react-query'
import type { Operation } from '@/shared/operations/contracts'
import { taskQueryKeys } from '@/features/tasks/queries'
import { queryKeys } from '@/shared/http/api'
const worldInputKinds = new Set(['world_restore', 'chunk_prune_apply', 'snapshot_restore', 'snapshot_backup', 'archive_extract', 'file_write', 'file_create', 'file_delete', 'file_rename', 'file_upload'])

export function worldOperationResources(operation: Operation): QueryKey[] {
  if (operation.kind === 'map_initialize') {
    return operation.resources.flatMap(({ server_id: id }) => id
      ? [queryKeys.map.status(id), queryKeys.map.regionsForServer(id)] : [])
  }
  if (!worldInputKinds.has(operation.kind) && operation.kind !== 'chunk_prune_preview') return []
  const keys: QueryKey[] = [taskQueryKeys.all]
  if (operation.resources.some(resource => resource.kind === 'files' && !resource.server_id)) {
    keys.push(queryKeys.map.all, queryKeys.worldRestore.all, queryKeys.ftbClaims.all, queryKeys.chunkPrune.all, queryKeys.serverMaintenance.all)
  }
  for (const { server_id: id } of operation.resources) {
    if (!id) continue
    keys.push(queryKeys.chunkPrune.state(id))
    if (operation.kind === 'chunk_prune_preview') continue
    keys.push(queryKeys.map.status(id), queryKeys.map.regionsForServer(id),
      queryKeys.worldRestore.layout(id), queryKeys.worldRestore.dimensionLabels(id),
      queryKeys.worldRestore.playerLocations(id), queryKeys.ftbClaims.claims(id),
      queryKeys.worldRestore.history(id), queryKeys.worldRestore.restorationsForServer(id),
      queryKeys.worldRestore.eligibleForServer(id), queryKeys.serverMaintenance.detail(id))
  }
  return keys
}
