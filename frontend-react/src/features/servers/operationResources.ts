import type { QueryKey } from '@tanstack/react-query'
import type { Operation } from '@/shared/operations/contracts'
import { queryKeys } from '@/shared/http/api'
import { taskQueryKeys } from '@/features/tasks/queries'

export function serversOperationResources(operation: Operation): QueryKey[] {
  if (!(operation.kind.startsWith('server_'))) return []
  return [taskQueryKeys.all, queryKeys.servers(), queryKeys.system.info(), queryKeys.serverInfos.all, queryKeys.serverRuntimes.all, queryKeys.serverStatuses.all, queryKeys.serverMaintenance.all, queryKeys.players.all, queryKeys.cron.all, queryKeys.restartSchedule.all, queryKeys.dns.all, queryKeys.files.all, queryKeys.selfCheck.all]
}
