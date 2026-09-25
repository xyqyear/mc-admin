import { shouldRetryQuery } from '@/shared/http/api'
import { useQuery } from '@tanstack/react-query'

import { selfCheckApi } from '@/features/health/api'
import { queryKeys } from '@/shared/http/api'

export const useSelfCheckCatalog = () => {
  return useQuery({
    queryKey: queryKeys.selfCheck.catalog(),
    queryFn: selfCheckApi.getCatalog,
    staleTime: 5 * 60 * 1000,
    retry: (failureCount, error) => shouldRetryQuery(failureCount, error, 2),
  })
}

export const useSelfCheckStatus = () => {
  return useQuery({
    queryKey: queryKeys.selfCheck.status(),
    queryFn: selfCheckApi.getStatus,
    staleTime: 30 * 1000,
    refetchInterval: 60 * 1000,
    retry: (failureCount, error) => shouldRetryQuery(failureCount, error, 2),
  })
}

export const useSelfCheckRuns = (
  params: { limit?: number; offset?: number } = {}
) => {
  return useQuery({
    queryKey: queryKeys.selfCheck.runs(params),
    queryFn: () => selfCheckApi.getRuns(params),
    staleTime: 30 * 1000,
    retry: (failureCount, error) => shouldRetryQuery(failureCount, error, 2),
  })
}

export const useSelfCheckRun = (runId: string | null) => {
  return useQuery({
    queryKey: queryKeys.selfCheck.run(runId!),
    queryFn: () => selfCheckApi.getRun(runId!),
    enabled: !!runId,
    staleTime: 30 * 1000,
    retry: (failureCount, error) => shouldRetryQuery(failureCount, error, 2),
  })
}
