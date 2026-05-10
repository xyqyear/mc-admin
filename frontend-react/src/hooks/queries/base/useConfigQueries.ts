import { useQuery } from '@tanstack/react-query'
import { queryKeys } from '@/utils/api'
import * as configApi from '@/hooks/api/configApi'

export const useConfigModules = () => {
  return useQuery({
    queryKey: queryKeys.config.modules(),
    queryFn: configApi.listAllModules,
    staleTime: 5 * 60 * 1000,
    refetchOnWindowFocus: false,
  })
}

export const useModuleConfig = (moduleName: string | null) => {
  return useQuery({
    queryKey: queryKeys.config.moduleConfig(moduleName!),
    queryFn: () => configApi.getModuleConfig(moduleName!),
    enabled: !!moduleName,
    staleTime: 2 * 60 * 1000,
    refetchOnWindowFocus: false,
  })
}

export const useModuleSchema = (moduleName: string | null) => {
  return useQuery({
    queryKey: queryKeys.config.moduleSchema(moduleName!),
    queryFn: () => configApi.getModuleSchema(moduleName!),
    enabled: !!moduleName,
    // Schemas rarely change.
    staleTime: 10 * 60 * 1000,
    refetchOnWindowFocus: false,
  })
}
