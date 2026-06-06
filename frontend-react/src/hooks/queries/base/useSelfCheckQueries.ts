import { useQuery } from '@tanstack/react-query'

import { selfCheckApi } from '@/hooks/api/selfCheckApi'
import { queryKeys } from '@/utils/api'

export const useSelfCheckCatalog = () => {
  return useQuery({
    queryKey: queryKeys.selfCheck.catalog(),
    queryFn: selfCheckApi.getCatalog,
    staleTime: 5 * 60 * 1000,
    retry: 2,
  })
}

export const useSelfCheckStatus = () => {
  return useQuery({
    queryKey: queryKeys.selfCheck.status(),
    queryFn: selfCheckApi.getStatus,
    staleTime: 30 * 1000,
    refetchInterval: 60 * 1000,
    retry: 2,
  })
}

export const useSelfCheckRuns = (
  params: { limit?: number; offset?: number } = {}
) => {
  return useQuery({
    queryKey: queryKeys.selfCheck.runs(params),
    queryFn: () => selfCheckApi.getRuns(params),
    staleTime: 30 * 1000,
    retry: 2,
  })
}

export const useSelfCheckRun = (runId: string | null) => {
  return useQuery({
    queryKey: queryKeys.selfCheck.run(runId!),
    queryFn: () => selfCheckApi.getRun(runId!),
    enabled: !!runId,
    staleTime: 30 * 1000,
    retry: 2,
  })
}

export const useSelfCheckQueries = () => {
  return {
    useSelfCheckCatalog,
    useSelfCheckStatus,
    useSelfCheckRuns,
    useSelfCheckRun,
  }
}
