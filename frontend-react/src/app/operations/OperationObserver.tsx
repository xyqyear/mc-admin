import { useEffect } from 'react'
import { useQueryClient, type QueryClient, type QueryKey } from '@tanstack/react-query'
import { queryKeys } from '@/shared/http/api'
import { isTerminalOperation, type Operation, type OperationChanges } from '@/shared/operations/contracts'
import { configurationOperationResources } from '@/features/configuration/operationResources'
import { filesOperationResources } from '@/features/files/operationResources'
import { worldOperationResources, resetMapRevision, updateMapRevision } from '@/features/world/operationResources'
import { serversOperationResources } from '@/features/servers/operationResources'
import { healthOperationResources } from '@/features/health/operationResources'
import { dnsOperationResources } from '@/features/dns/operationResources'
import { backupsOperationResources } from '@/features/backups/operationResources'
import { subscribeTaskEvents, taskQueryKeys } from '@/features/tasks/queries'

const resourceRegistrations: ((operation: Operation) => QueryKey[])[] = [configurationOperationResources, filesOperationResources, worldOperationResources, serversOperationResources, healthOperationResources, dnsOperationResources, backupsOperationResources]
const resetResources: QueryKey[] = [
  queryKeys.compose.all, queryKeys.templates.all, queryKeys.servers(), queryKeys.monitoring.all,
  queryKeys.serverInfos.all, queryKeys.monitoring.all,
  queryKeys.players.all, queryKeys.cron.all, queryKeys.restartSchedule.all, queryKeys.dns.all,
  queryKeys.files.all, queryKeys.selfCheck.all, queryKeys.archive.all,
  queryKeys.snapshots.all, queryKeys.snapshots.rulesAll(), queryKeys.map.all,
  queryKeys.worldRestore.all, queryKeys.ftbClaims.all, queryKeys.chunkPrune.all, taskQueryKeys.all,
]

interface Checkpoint { cursor: string; active_count: number }

async function processChanges(client: QueryClient, sessionId: string, data: OperationChanges, signal: AbortSignal): Promise<void> {
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
    signal.throwIfAborted()
    client.setQueryData<Checkpoint>(queryKeys.operations.checkpoint(sessionId), { cursor: data.next_cursor, active_count: data.active_count })
}

export function OperationObserver({ sessionId }: { sessionId: string }) {
  const client = useQueryClient()
  useEffect(() => {
    client.setQueryDefaults(queryKeys.operations.all, { gcTime: Infinity })
    return subscribeTaskEvents(client, {
      getOperationCursor: () => client.getQueryData<Checkpoint>(queryKeys.operations.checkpoint(sessionId))?.cursor,
      onOperations: (changes, signal) => processChanges(client, sessionId, changes, signal),
    })
  }, [client, sessionId])
  return null
}
