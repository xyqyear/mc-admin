import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { queryKeys } from '@/utils/api'
import * as configApi from '@/hooks/api/configApi'
import * as dnsApi from '@/hooks/api/dnsApi'

// Hooks invoked after a successful module config update; each is responsible
// for its own gating (e.g. DNS only triggers a sync if it is enabled).
const MODULE_POST_UPDATE_ACTIONS: Record<string, () => Promise<void>> = {
  dns: async () => {
    try {
      const enabledResponse = await dnsApi.getDNSEnabled()
      if (enabledResponse.enabled) {
        await dnsApi.updateDNS()
        toast.success('DNS配置已更新，DNS记录同步成功')
      } else {
        toast.info('DNS配置已更新，但DNS管理器未启用，跳过记录同步')
      }
    } catch (error: any) {
      toast.warning(`DNS配置已更新，但记录同步失败: ${error.message}`)
    }
  },
}

export const useUpdateModuleConfig = () => {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ moduleName, configData }: { moduleName: string; configData: Record<string, any> }) =>
      configApi.updateModuleConfig(moduleName, configData),
    onSuccess: async (data, variables) => {
      toast.success(data.message || '配置更新成功')

      queryClient.invalidateQueries({
        queryKey: queryKeys.config.moduleConfig(variables.moduleName)
      })
      queryClient.invalidateQueries({
        queryKey: queryKeys.config.modules()
      })

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
      toast.error(`更新失败: ${errorMessage}`)
    },
  })
}

export const useResetModuleConfig = () => {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (moduleName: string) => configApi.resetModuleConfig(moduleName),
    onSuccess: (data, moduleName) => {
      toast.success(data.message || '配置重置成功')

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
      toast.error(`重置失败: ${errorMessage}`)
    },
  })
}
