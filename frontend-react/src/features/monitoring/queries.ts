import { queryOptions, useQuery } from '@tanstack/react-query'
import { useCurrentUser } from '@/features/users/queries'
import { queryKeys } from '@/shared/http/api'
import { getMonitoring } from './api'
import type { MonitoringSnapshot } from './contracts'

export const monitoringQueryOptions = (userId: number | null) => queryOptions({
  queryKey: queryKeys.monitoring.snapshot(userId),
  queryFn: ({ signal }) => getMonitoring(signal),
  staleTime: 0,
  retry: false,
  enabled: false,
})

export function useMonitoring<T = MonitoringSnapshot>(select?: (data: MonitoringSnapshot) => T) {
  const user = useCurrentUser()
  return useQuery({ ...monitoringQueryOptions(user.data?.id ?? null), select })
}

export function useServerMonitoring(serverId: string) {
  return useMonitoring(data => data.servers[serverId])
}

export function useServerStatus(serverId: string) {
  const result = useMonitoring(data => {
    const sample = data.servers[serverId]?.status
    return sample?.quality === 'ready' ? sample.value ?? undefined : undefined
  })
  return { ...result, data: result.isError ? undefined : result.data }
}

export function useServerMaintenance(serverId: string) {
  return useMonitoring(data => data.servers[serverId]?.maintenance)
}
