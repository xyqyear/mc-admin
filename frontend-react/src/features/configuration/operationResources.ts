import { queryKeys } from '@/shared/http/api'
import { taskQueryKeys } from '@/features/tasks/queries'
import type { Operation } from '@/shared/operations/contracts'

export function configurationOperationResources(operation: Operation) {
  if (!['server_rebuild', 'configuration_apply'].includes(operation.kind)) return []
  return [taskQueryKeys.all, queryKeys.servers(), ...operation.resources.flatMap(resource => {
    const id = resource.server_id
    if (!id) return []
    return [
      queryKeys.compose.detail(id),
      queryKeys.templates.serverConfig(id),
      queryKeys.templates.serverConfigPreview(id),
      queryKeys.serverInfos.detail(id),
      queryKeys.monitoring.all,
      queryKeys.players.serverOnline(id),
    ]
  })]
}
