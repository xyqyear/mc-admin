import { useServerInfo, useRestartSchedule } from './queries'
import { useServerMonitoring } from '@/features/monitoring/queries'

export const useServerDetailData = (serverId: string) => {
  const configQuery = useServerInfo(serverId)
  const monitoring = useServerMonitoring(serverId)
  const restartScheduleQuery = useRestartSchedule(serverId)
  const samples = monitoring.data?.generation === configQuery.data?.serverGeneration ? monitoring.data : undefined
  const status = !monitoring.isError && samples?.status.quality === 'ready' ? samples.status.value ?? undefined : undefined
  return {
    serverInfo: configQuery.data,
    samples,
    monitoringFailed: monitoring.isError,
    status,
    restartSchedule: restartScheduleQuery.data,
    restartScheduleQuery,
    isLoading: configQuery.isLoading,
    isError: configQuery.isError,
    error: configQuery.error,
    hasServerInfo: !!configQuery.data,
    isHealthy: status === 'HEALTHY',
  }
}
