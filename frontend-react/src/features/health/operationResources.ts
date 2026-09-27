import type { QueryKey } from '@tanstack/react-query'
import type { Operation } from '@/shared/operations/contracts'
import { queryKeys } from '@/shared/http/api'
import { taskQueryKeys } from '@/features/tasks/queries'

export function healthOperationResources(operation: Operation): QueryKey[] {
  if (!(operation.kind === 'self_check')) return []
  return [taskQueryKeys.all, queryKeys.selfCheck.all]
}
