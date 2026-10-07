import { useQuery, useQueryClient, type QueryClient, type QueryKey } from '@tanstack/react-query'
import { api, queryKeys } from '@/shared/http/api'
import { isTerminalOperation, type Operation, type OperationChanges } from '@/shared/operations/contracts'
import { configurationOperationResources } from '@/features/configuration/operationResources'
import { filesOperationResources } from '@/features/files/operationResources'
import { worldOperationResources, resetMapRevision, updateMapRevision } from '@/features/world/operationResources'
import { serversOperationResources } from '@/features/servers/operationResources'
import { healthOperationResources } from '@/features/health/operationResources'
import { dnsOperationResources } from '@/features/dns/operationResources'
import { backupsOperationResources } from '@/features/backups/operationResources'
import { taskQueryKeys } from '@/features/tasks/queries'

const resourceRegistrations: ((operation: Operation) => QueryKey[])[] = [configurationOperationResources, filesOperationResources, worldOperationResources, serversOperationResources, healthOperationResources, dnsOperationResources, backupsOperationResources]
const resetResources: QueryKey[] = [
  queryKeys.compose.all, queryKeys.templates.all, queryKeys.servers(), queryKeys.system.info(),
  queryKeys.serverInfos.all, queryKeys.serverRuntimes.all, queryKeys.serverStatuses.all, queryKeys.serverMaintenance.all,
  queryKeys.players.all, queryKeys.cron.all, queryKeys.restartSchedule.all, queryKeys.dns.all,
  queryKeys.files.all, queryKeys.selfCheck.all, queryKeys.archive.all,
  queryKeys.snapshots.all, queryKeys.snapshots.rulesAll(), queryKeys.map.all,
  queryKeys.worldRestore.all, queryKeys.ftbClaims.all, queryKeys.chunkPrune.all, taskQueryKeys.all,
]

interface Checkpoint { cursor: string; active_count: number }

async function readChanges(client: QueryClient, sessionId: string, signal: AbortSignal): Promise<Checkpoint> {
  client.setQueryDefaults(queryKeys.operations.all, { gcTime: Infinity })
  const checkpointKey = queryKeys.operations.checkpoint(sessionId)
  let checkpoint = client.getQueryData<Checkpoint>(checkpointKey)
  for (;;) {
    signal.throwIfAborted()
    const { data } = await api.get<OperationChanges>('/operations/changes', { params: { cursor: checkpoint?.cursor, limit: 200 }, signal })
    signal.throwIfAborted()
    const keys = new Map<string, QueryKey>()
    if (data.reset_required) {
      resetMapRevision(client, data.next_cursor)
      for (const key of resetResources) keys.set(JSON.stringify(key), key)
    } else {
      for (const operation of data.items) {
        if (!isTerminalOperation(operation)) continue
        updateMapRevision(client, operation, operation.sequence)
        for (const registration of resourceRegistrations) {
          for (const key of registration(operation)) keys.set(JSON.stringify(key), key)
        }
      }
    }
    await Promise.all([...keys.values()].map(queryKey => client.cancelQueries({ queryKey })))
    signal.throwIfAborted()
    for (const key of keys.values()) void client.invalidateQueries({ queryKey: key })
    checkpoint = { cursor: data.next_cursor, active_count: data.active_count }
    // Cancellation can roll back the observing query, so keep processed progress separately.
    client.setQueryData(checkpointKey, checkpoint)
    if (!data.has_more) return checkpoint
  }
}

export function OperationObserver({ sessionId }: { sessionId: string }) {
  const client = useQueryClient()
  useQuery<Checkpoint | null>({
    queryKey: queryKeys.operations.session(sessionId),
    queryFn: ({ signal }) => readChanges(client, sessionId, signal),
    initialData: null,
    staleTime: 0,
    refetchOnReconnect: 'always',
    refetchOnWindowFocus: 'always',
    refetchInterval: query => query.state.status === 'error' || !query.state.data || query.state.data.active_count > 0 ? 2000 : 30000,
    refetchIntervalInBackground: false,
  })
  return null
}
