import type { QueryKey } from '@tanstack/react-query'
import type { Operation } from '@/shared/operations/contracts'
import { taskQueryKeys } from '@/features/tasks/queries'
import { queryKeys } from '@/shared/http/api'

export const fileOperationKinds = new Set([
  'file_write', 'file_create', 'file_delete', 'file_rename', 'file_upload',
  'file_ownership_repair', 'archive_create', 'archive_extract', 'archive_publish',
  'archive_write', 'snapshot_restore', 'snapshot_backup',
  'world_restore', 'chunk_prune_apply',
])

export function filesOperationResources(operation: Operation): QueryKey[] {
  if (!fileOperationKinds.has(operation.kind)) return []
  const keys: QueryKey[] = [taskQueryKeys.all]
  if (operation.kind.startsWith('archive_')) keys.push(queryKeys.archive.all)
  if (operation.kind.startsWith('snapshot_') || operation.kind === 'world_restore') keys.push(queryKeys.snapshots.all)
  if (operation.resources.some(resource => resource.kind === 'files' && !resource.server_id)) {
    keys.push(queryKeys.files.all, queryKeys.serverRuntimes.all, queryKeys.serverInfos.all, queryKeys.serverMaintenance.all)
  }
  for (const { server_id: id } of operation.resources) {
    if (!id) continue
    keys.push(queryKeys.files.lists(id), queryKeys.serverRuntimes.disk(id), queryKeys.serverInfos.detail(id), queryKeys.serverMaintenance.detail(id))
  }
  return keys
}
