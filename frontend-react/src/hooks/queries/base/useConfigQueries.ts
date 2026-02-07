import { useQuery } from '@tanstack/react-query'
import { queryKeys } from '@/utils/api'
import * as configApi from '@/hooks/api/configApi'

/**
 * Hook to get all configuration modules
 */
export const useConfigModules = () => {
  return useQuery({
    queryKey: queryKeys.config.modules(),
    queryFn: configApi.listAllModules,
    staleTime: 5 * 60 * 1000, // 5 minutes - modules don't change often
    refetchOnWindowFocus: false,
  })
}

/**
 * Hook to get configuration data for a specific module
 */
export const useModuleConfig = (moduleName: string | null) => {
  return useQuery({
    queryKey: queryKeys.config.moduleConfig(moduleName!),
    queryFn: () => configApi.getModuleConfig(moduleName!),
    enabled: !!moduleName,
    staleTime: 2 * 60 * 1000, // 2 minutes - config can change more frequently
    refetchOnWindowFocus: false,
  })
}

/**
 * Hook to get schema information for a specific module
 */
export const useModuleSchema = (moduleName: string | null) => {
  return useQuery({
    queryKey: queryKeys.config.moduleSchema(moduleName!),
    queryFn: () => configApi.getModuleSchema(moduleName!),
    enabled: !!moduleName,
    staleTime: 10 * 60 * 1000, // 10 minutes - schemas rarely change
    refetchOnWindowFocus: false,
  })
}
