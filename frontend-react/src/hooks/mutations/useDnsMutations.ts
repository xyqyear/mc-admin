import { useMutation, useQueryClient } from '@tanstack/react-query'
import { App } from 'antd'
import { queryKeys } from '@/utils/api'
import * as dnsApi from '@/hooks/api/dnsApi'

/**
 * DNS update mutation for manual triggering of DNS and router updates
 */
export const useUpdateDNS = () => {
  const queryClient = useQueryClient()
  const { message } = App.useApp()

  return useMutation({
    mutationFn: dnsApi.updateDNS,
    onSuccess: (data) => {
      message.success(data.message || 'DNS和路由更新成功')

      // Invalidate related queries to refresh data
      queryClient.invalidateQueries({ queryKey: queryKeys.dns.status() })
      queryClient.invalidateQueries({ queryKey: queryKeys.dns.records() })
      queryClient.invalidateQueries({ queryKey: queryKeys.dns.routes() })
    },
    onError: (error: any) => {
      message.error(`DNS更新失败: ${error.message}`)
    },
  })
}

/**
 * Manual refresh of DNS-related data
 */
export const useRefreshDNSData = () => {
  const queryClient = useQueryClient()
  const { message } = App.useApp()

  return useMutation({
    mutationFn: async () => {
      // Force refresh all DNS-related queries
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.dns.status() }),
        queryClient.invalidateQueries({ queryKey: queryKeys.dns.records() }),
        queryClient.invalidateQueries({ queryKey: queryKeys.dns.routes() }),
        queryClient.invalidateQueries({ queryKey: queryKeys.dns.enabled() }),
      ])

      // Wait for the queries to complete
      await Promise.all([
        queryClient.refetchQueries({ queryKey: queryKeys.dns.status() }),
        queryClient.refetchQueries({ queryKey: queryKeys.dns.records() }),
        queryClient.refetchQueries({ queryKey: queryKeys.dns.routes() }),
        queryClient.refetchQueries({ queryKey: queryKeys.dns.enabled() }),
      ])
    },
    onSuccess: () => {
      message.success('DNS数据已刷新')
    },
    onError: (error: any) => {
      message.error(`刷新失败: ${error.message}`)
    },
  })
}