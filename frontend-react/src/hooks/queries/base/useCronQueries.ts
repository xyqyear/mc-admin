import { useQuery } from '@tanstack/react-query'
import { cronApi } from '@/hooks/api/cronApi'
import { queryKeys } from '@/utils/api'

// Query for getting all registered cron job types
export const useRegisteredCronJobs = () => {
  return useQuery({
    queryKey: queryKeys.cron.registeredTypes(),
    queryFn: cronApi.getRegisteredCronJobs,
    staleTime: 5 * 60 * 1000, // 5 minutes - registered types rarely change
    retry: 2
  })
}

// Query for getting all cron jobs with optional filtering
export const useAllCronJobs = (filters?: {
  identifier?: string
  status?: string[]
}) => {
  return useQuery({
    queryKey: queryKeys.cron.list(filters),
    queryFn: () => cronApi.getAllCronJobs(filters),
    staleTime: 1 * 60 * 1000, // 1 minute - job list changes frequently
    refetchInterval: 30 * 1000, // Auto-refresh every 30 seconds
    retry: 2
  })
}

// Query for getting specific cron job details
export const useCronJob = (cronjobId: string | null) => {
  return useQuery({
    queryKey: queryKeys.cron.detail(cronjobId!),
    queryFn: () => cronApi.getCronJob(cronjobId!),
    enabled: !!cronjobId,
    staleTime: 2 * 60 * 1000, // 2 minutes - job config changes occasionally
    retry: 2
  })
}

// Query for getting cron job execution history
export const useCronJobExecutions = (cronjobId: string | null, limit: number = 50) => {
  return useQuery({
    queryKey: queryKeys.cron.executions(cronjobId!, limit),
    queryFn: () => cronApi.getCronJobExecutions(cronjobId!, limit),
    enabled: !!cronjobId,
    staleTime: 30 * 1000, // 30 seconds - execution history updates frequently
    refetchInterval: 30 * 1000, // Auto-refresh every 30 seconds
    retry: 2
  })
}

// Query for getting next run time
export const useCronJobNextRunTime = (cronjobId: string | null) => {
  return useQuery({
    queryKey: queryKeys.cron.nextRunTime(cronjobId!),
    queryFn: () => cronApi.getCronJobNextRunTime(cronjobId!),
    enabled: !!cronjobId,
    staleTime: 30 * 1000, // 30 seconds - next run time changes frequently
    refetchInterval: 60 * 1000, // Auto-refresh every minute
    retry: 2
  })
}

// Combined hook for cron job queries (used in detail views)
export const useCronQueries = () => {
  return {
    useRegisteredCronJobs,
    useAllCronJobs,
    useCronJob,
    useCronJobExecutions,
    useCronJobNextRunTime
  }
}