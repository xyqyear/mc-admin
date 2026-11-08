import { useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { getErrorMessage, queryKeys } from '@/shared/http/api'
import type { SettingsResource } from '@/features/settings/api'
import * as dnsApi from '@/features/dns/api'

export function useSettingsCommands<T>(resource: SettingsResource<T>) {
  const client = useQueryClient()
  const settled = (value: T) => {
    client.setQueryData(queryKeys.settings.detail(resource.key), value)
    if (resource.key === 'snapshots') {
      void client.invalidateQueries({ queryKey: queryKeys.snapshots.rulesAll() })
      void client.invalidateQueries({ queryKey: queryKeys.snapshots.all })
    }
    if (resource.key === 'dns') {
      void client.invalidateQueries({ queryKey: queryKeys.dns.all })
    }
    if (resource.key === 'self-check') {
      void client.invalidateQueries({ queryKey: queryKeys.selfCheck.all })
    }
  }
  const onError = (error: unknown) => toast.error(getErrorMessage(error) || '配置保存失败')
  return {
    save: useMutation({ mutationFn: resource.replace, onSuccess: settled, onError }),
    reset: useMutation({ mutationFn: resource.reset, onSuccess: settled, onError }),
  }
}

export function useDNSSettingsSync() {
  const client = useQueryClient()
  return async () => {
    try {
      if ((await dnsApi.getDNSEnabled()).enabled) {
        await dnsApi.updateDNS()
        toast.success('DNS 记录同步成功')
      } else {
        toast.info('DNS 管理未启用，已保存配置')
      }
    } catch (error) {
      toast.warning(`配置已保存，但 DNS 同步失败：${getErrorMessage(error)}`)
    } finally {
      void client.invalidateQueries({ queryKey: queryKeys.dns.all })
    }
  }
}
