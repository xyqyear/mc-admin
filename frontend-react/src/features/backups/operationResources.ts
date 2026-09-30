import type { QueryKey } from '@tanstack/react-query'
import type { Operation } from '@/shared/operations/contracts'
import { queryKeys } from '@/shared/http/api'
import { taskQueryKeys } from '@/features/tasks/queries'

export function backupsOperationResources(operation: Operation): QueryKey[] {
  return operation.kind.startsWith('snapshot_') || operation.kind === 'world_restore'
    ? [queryKeys.snapshots.all, taskQueryKeys.all]
    : []
}
