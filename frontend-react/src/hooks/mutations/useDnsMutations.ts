import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { queryKeys } from '@/utils/api'
import * as dnsApi from '@/hooks/api/dnsApi'

export const useUpdateDNS = () => {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: dnsApi.updateDNS,
    onSuccess: (data) => {
      toast.success(data.message || 'DNS和路由更新成功')

      queryClient.invalidateQueries({ queryKey: queryKeys.dns.status() })
      queryClient.invalidateQueries({ queryKey: queryKeys.dns.records() })
      queryClient.invalidateQueries({ queryKey: queryKeys.dns.routes() })
    },
    onError: (error: any) => {
      toast.error(`DNS更新失败: ${error.message}`)
    },
  })
}

export const useRefreshDNSData = () => {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async () => {
      // refetchQueries instead of invalidate-then-refetch to avoid duplicate requests.
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

// Triggered after server operations; gates the update on the DNS module being
// enabled so the disabled state does not surface as an error.
export const useAutoUpdateDNS = () => {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async () => {
      const enabledResponse = await dnsApi.getDNSEnabled()
      if (!enabledResponse.enabled) {
        return { skipped: true, message: 'DNS管理器未启用，跳过自动更新' }
      }

      const updateResponse = await dnsApi.updateDNS()
      return { skipped: false, ...updateResponse }
    },
    onSuccess: (data) => {
      if (!data.skipped) {
        toast.success('DNS记录已自动更新')
        queryClient.invalidateQueries({ queryKey: queryKeys.dns.status() })
        queryClient.invalidateQueries({ queryKey: queryKeys.dns.records() })
        queryClient.invalidateQueries({ queryKey: queryKeys.dns.routes() })
      }
    },
    onError: (error: any) => {
      toast.error(`DNS自动更新失败: ${error.message}`)
    },
  })
}