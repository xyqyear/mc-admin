import type { QueryClient, QueryKey } from '@tanstack/react-query'
import type { Operation } from '@/shared/operations/contracts'
import { taskQueryKeys } from '@/features/tasks/queries'
import { queryKeys } from '@/shared/http/api'
import { latestMapRevision, type MapRevision } from './map/revision'
export { resetMapRevision } from './map/revision'
const worldInputKinds = new Set(['world_restore', 'chunk_prune_apply', 'snapshot_restore', 'snapshot_backup', 'archive_extract', 'file_write', 'file_create', 'file_delete', 'file_rename', 'file_upload'])

export function updateMapRevision(client: QueryClient, operation: Operation, sequence?: number) {
  if (!(operation.data_changed && worldInputKinds.has(operation.kind)) && operation.kind !== 'map_initialize') return
  const time = Date.parse(operation.ended_at ?? operation.updated_at)
  if (!Number.isFinite(time)) return
  const revision = { time, id: operation.operation_id, sequence }
  client.setQueryDefaults(queryKeys.map.revisions(), { gcTime: Infinity })
  const global = operation.resources.some(resource => resource.kind === 'files' && !resource.server_id)
  const targets = global ? [undefined] : [...new Set(operation.resources.flatMap(resource => resource.server_id ? [resource.server_id] : []))]
  for (const id of targets) {
    client.setQueryData<MapRevision | null>(queryKeys.map.revision(id), current => latestMapRevision(current, revision))
  }
}

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
      queryKeys.serverMaintenance.detail(id))
  }
  return keys
}
