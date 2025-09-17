import { useMutation, useQueryClient } from '@tanstack/react-query'
import { message } from 'antd'
import { queryKeys } from '@/utils/api'
import * as configApi from '@/hooks/api/configApi'

/**
 * Hook to update module configuration
 */
export const useUpdateModuleConfig = () => {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ moduleName, configData }: { moduleName: string; configData: Record<string, any> }) =>
      configApi.updateModuleConfig(moduleName, configData),
    onSuccess: (data, variables) => {
      message.success(data.message || '配置更新成功')

      // Invalidate related queries
      queryClient.invalidateQueries({
        queryKey: queryKeys.config.moduleConfig(variables.moduleName)
      })
      queryClient.invalidateQueries({
        queryKey: queryKeys.config.modules()
      })
    },
    onError: (error: any) => {
      const errorMessage = error.response?.data?.detail || error.message || '配置更新失败'
      message.error(`更新失败: ${errorMessage}`)
    },
  })
}

/**
 * Hook to reset module configuration to defaults
 */
export const useResetModuleConfig = () => {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (moduleName: string) => configApi.resetModuleConfig(moduleName),
    onSuccess: (data, moduleName) => {
      message.success(data.message || '配置重置成功')

      // Invalidate related queries
      queryClient.invalidateQueries({
        queryKey: queryKeys.config.moduleConfig(moduleName)
      })
      queryClient.invalidateQueries({
        queryKey: queryKeys.config.modules()
      })
    },
    onError: (error: any) => {
      const errorMessage = error.response?.data?.detail || error.message || '配置重置失败'
      message.error(`重置失败: ${errorMessage}`)
    },
  })
}