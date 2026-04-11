import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { queryKeys } from '@/utils/api'
import * as dnsApi from '@/hooks/api/dnsApi'

/**
 * DNS update mutation for manual triggering of DNS and router updates
 */
export const useUpdateDNS = () => {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: dnsApi.updateDNS,
    onSuccess: (data) => {
      toast.success(data.message || 'DNS和路由更新成功')

      // Invalidate related queries to refresh data
      queryClient.invalidateQueries({ queryKey: queryKeys.dns.status() })
      queryClient.invalidateQueries({ queryKey: queryKeys.dns.records() })
      queryClient.invalidateQueries({ queryKey: queryKeys.dns.routes() })
    },
    onError: (error: any) => {
      toast.error(`DNS更新失败: ${error.message}`)
    },
  })
}

/**
 * Manual refresh of DNS-related data
 */
export const useRefreshDNSData = () => {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async () => {
      // Force refresh all DNS-related queries
      // Use refetchQueries instead of invalidateQueries + refetchQueries to avoid double requests
      await Promise.all([
        queryClient.refetchQueries({ queryKey: queryKeys.dns.status() }),
        queryClient.refetchQueries({ queryKey: queryKeys.dns.records() }),
        queryClient.refetchQueries({ queryKey: queryKeys.dns.routes() }),
        queryClient.refetchQueries({ queryKey: queryKeys.dns.enabled() }),
      ])
    },
    onSuccess: () => {
      toast.success('DNS数据已刷新')
    },
    onError: (error: any) => {
      toast.error(`刷新失败: ${error.message}`)
    },
  })
}

/**
 * Auto DNS update mutation for triggering after server operations
 * This version checks DNS enabled status internally and provides user feedback
 */
export const useAutoUpdateDNS = () => {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async () => {
      // Check if DNS is enabled first
      const enabledResponse = await dnsApi.getDNSEnabled()
      if (!enabledResponse.enabled) {
        return { skipped: true, message: 'DNS管理器未启用，跳过自动更新' }
      }

      // If enabled, trigger DNS update
      const updateResponse = await dnsApi.updateDNS()
      return { skipped: false, ...updateResponse }
    },
    onSuccess: (data) => {
      if (!data.skipped) {
        // Show success message and invalidate queries
        toast.success('DNS记录已自动更新')
        queryClient.invalidateQueries({ queryKey: queryKeys.dns.status() })
        queryClient.invalidateQueries({ queryKey: queryKeys.dns.records() })
        queryClient.invalidateQueries({ queryKey: queryKeys.dns.routes() })
      }
    },
    onError: (error: any) => {
      // Show error message to user
      toast.error(`DNS自动更新失败: ${error.message}`)
    },
  })
}