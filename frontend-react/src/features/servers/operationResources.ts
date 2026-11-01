import type { QueryKey } from '@tanstack/react-query'
import type { Operation } from '@/shared/operations/contracts'
import { queryKeys } from '@/shared/http/api'
import { taskQueryKeys } from '@/features/tasks/queries'

export function serversOperationResources(operation: Operation): QueryKey[] {
  if (!(operation.kind.startsWith('server_'))) return []
  return [taskQueryKeys.all, queryKeys.servers(), queryKeys.monitoring.all, queryKeys.serverInfos.all, queryKeys.monitoring.all, queryKeys.players.all, queryKeys.cron.all, queryKeys.restartSchedule.all, queryKeys.dns.all, queryKeys.files.all, queryKeys.selfCheck.all]
}
