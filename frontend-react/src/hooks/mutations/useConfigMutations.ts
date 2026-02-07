import { useMutation, useQueryClient } from '@tanstack/react-query'
import { message } from 'antd'
import { queryKeys } from '@/utils/api'
import * as configApi from '@/hooks/api/configApi'
import * as dnsApi from '@/hooks/api/dnsApi'

// Post-update actions for different modules
// Each action function handles its own conditions internally
const MODULE_POST_UPDATE_ACTIONS: Record<string, () => Promise<void>> = {
  dns: async () => {
    // Check if DNS is enabled before triggering update
    try {
      const enabledResponse = await dnsApi.getDNSEnabled()
      if (enabledResponse.enabled) {
        await dnsApi.updateDNS()
        message.success('DNS配置已更新，DNS记录同步成功')
      } else {
        message.info('DNS配置已更新，但DNS管理器未启用，跳过记录同步')
      }
    } catch (error: any) {
      message.warning(`DNS配置已更新，但记录同步失败: ${error.message}`)
    }
  },
  // Add more module post-update actions here as needed
  // example: async () => { ... },
}

/**
 * Hook to update module configuration
 */
export const useUpdateModuleConfig = () => {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ moduleName, configData }: { moduleName: string; configData: Record<string, any> }) =>
      configApi.updateModuleConfig(moduleName, configData),
    onSuccess: async (data, variables) => {
      message.success(data.message || '配置更新成功')

      // Invalidate related queries
      queryClient.invalidateQueries({
        queryKey: queryKeys.config.moduleConfig(variables.moduleName)
      })
      queryClient.invalidateQueries({
        queryKey: queryKeys.config.modules()
      })

      // Execute post-update action if available for this module
      const postUpdateAction = MODULE_POST_UPDATE_ACTIONS[variables.moduleName]
      if (postUpdateAction) {
        await postUpdateAction()
      }

      if (variables.moduleName === 'dns') {
        queryClient.invalidateQueries({ queryKey: queryKeys.dns.enabled() })
        queryClient.invalidateQueries({ queryKey: queryKeys.dns.status() })
        queryClient.invalidateQueries({ queryKey: queryKeys.dns.records() })
        queryClient.invalidateQueries({ queryKey: queryKeys.dns.routes() })
      }
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

      if (moduleName === 'dns') {
        queryClient.invalidateQueries({ queryKey: queryKeys.dns.enabled() })
        queryClient.invalidateQueries({ queryKey: queryKeys.dns.status() })
        queryClient.invalidateQueries({ queryKey: queryKeys.dns.records() })
        queryClient.invalidateQueries({ queryKey: queryKeys.dns.routes() })
      }
    },
    onError: (error: any) => {
      const errorMessage = error.response?.data?.detail || error.message || '配置重置失败'
      message.error(`重置失败: ${errorMessage}`)
    },
  })
}
