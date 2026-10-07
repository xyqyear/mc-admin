import type { QueryKey } from '@tanstack/react-query'
import type { Operation } from '@/shared/operations/contracts'
import { queryKeys } from '@/shared/http/api'
import { taskQueryKeys } from '@/features/tasks/queries'

export function backupsOperationResources(operation: Operation): QueryKey[] {
  const keys: QueryKey[] = operation.kind.startsWith('snapshot_') || operation.kind === 'world_restore'
    ? [queryKeys.snapshots.all, taskQueryKeys.all] : []
  const changesRules = operation.data_changed && [
    'file_write', 'file_create', 'file_delete', 'file_rename', 'file_upload',
    'archive_extract', 'snapshot_restore', 'world_restore',
  ].includes(operation.kind)
  const changesServer = operation.data_changed && (operation.kind.startsWith('server_') || operation.kind === 'configuration_apply')
  if (!changesRules && !changesServer) return keys
  if (operation.resources.some(resource => resource.kind === 'files' && !resource.server_id)) {
    keys.push(queryKeys.snapshots.rulesAll())
  } else {
    for (const id of new Set(operation.resources.flatMap(resource => resource.server_id ? [resource.server_id] : []))) {
      keys.push(queryKeys.snapshots.rules(id))
    }
  }
  return keys
}
