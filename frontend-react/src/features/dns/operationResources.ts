import type { QueryKey } from '@tanstack/react-query'
import type { Operation } from '@/shared/operations/contracts'
import { queryKeys } from '@/shared/http/api'
import { taskQueryKeys } from '@/features/tasks/queries'

export function dnsOperationResources(operation: Operation): QueryKey[] {
  if (!(operation.kind === 'dns_update')) return []
  return [taskQueryKeys.all, queryKeys.dns.all]
}
