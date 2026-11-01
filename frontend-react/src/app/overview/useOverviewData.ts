import { useQueries } from '@tanstack/react-query'
import { serverOnlinePlayersQueryOptions } from '@/features/players/queries'
import { useServers } from '@/features/servers/queries'
import { useBackupRepositoryUsage } from '@/features/backups/queries'
import { useMonitoring } from '@/features/monitoring/queries'
import type { ServerStatus } from '@/features/servers/contracts'

export const useOverviewData = () => {
  const serversQuery = useServers()
  const monitoring = useMonitoring()
  const backupRepositoryQuery = useBackupRepositoryUsage()
  const servers = serversQuery.data ?? []
  const serverStatuses = Object.fromEntries(servers.map(server => {
    const status = monitoring.data?.servers[server.id]?.status
    return [server.id, !monitoring.isError && status?.quality === 'ready' ? status.value : undefined]
  }))
  const healthyIds = servers.filter(server => serverStatuses[server.id] === 'HEALTHY').map(server => server.id)
  const players = useQueries({ queries: healthyIds.map(serverOnlinePlayersQueryOptions) })
  const online = Object.fromEntries(healthyIds.map((id, index) => [id, players[index].data?.map(player => player.current_name) ?? []]))
  const enrichedServers = servers.map(server => ({
    ...server,
    samples: monitoring.data?.servers[server.id],
    maintenance: monitoring.data?.servers[server.id]?.maintenance,
    status: serverStatuses[server.id] ?? ('UNKNOWN' as ServerStatus),
    onlinePlayers: online[server.id] ?? [],
  }))
  return {
    enrichedServers,
    system: monitoring.data?.system,
    monitoringFailed: monitoring.isError,
    backupRepositoryUsage: backupRepositoryQuery.data,
    serverNum: servers.length,
    runningServers: Object.values(serverStatuses).filter(status => status && ['RUNNING', 'STARTING', 'HEALTHY'].includes(status)).length,
    onlinePlayerNum: Object.values(online).reduce((total, names) => total + names.length, 0),
    isLoading: serversQuery.isLoading,
    isStatusLoading: monitoring.isPending,
    isError: serversQuery.isError,
    error: serversQuery.error,
    refetch: () => Promise.all([
      serversQuery.refetch(), monitoring.refetch(), backupRepositoryQuery.refetch(),
      ...players.map(query => query.refetch()),
    ]),
  }
}
