import type { ApiError } from '@/shared/http/api'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { queryKeys } from '@/shared/http/api'
import * as dnsApi from '@/features/dns/api'

export const useUpdateDNS = () => {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: dnsApi.updateDNS,
    onSuccess: (data) => {
      toast.success(data.message || 'DNS和路由更新成功')
    },
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.dns.status() })
      void queryClient.invalidateQueries({ queryKey: queryKeys.dns.records() })
      void queryClient.invalidateQueries({ queryKey: queryKeys.dns.routes() })
    },
    onError: (error: ApiError) => {
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
        queryClient.refetchQueries({ queryKey: queryKeys.dns.status() }, { throwOnError: true }),
        queryClient.refetchQueries({ queryKey: queryKeys.dns.records() }, { throwOnError: true }),
        queryClient.refetchQueries({ queryKey: queryKeys.dns.routes() }, { throwOnError: true }),
        queryClient.refetchQueries({ queryKey: queryKeys.dns.enabled() }, { throwOnError: true }),
      ])
    },
    onSuccess: () => {
      toast.success('DNS数据已刷新')
    },
    onError: (error: ApiError) => {
      toast.error(`刷新失败: ${error.message}`)
    },
  })
}
