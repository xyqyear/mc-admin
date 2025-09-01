import { serverApi, type ServerListItem } from '@/hooks/api/serverApi'
import type { ServerStatus } from '@/types/ServerInfo'
import { queryKeys } from '@/utils/api'
import { useQueries } from '@tanstack/react-query'
import { useServerQueries } from './useServerQueries'

export const useServerPageQueries = (serverId: string) => {
  const { useServerInfo, useServerStatus, useServerRuntime } = useServerQueries()
  
  // 服务器概览页面数据
  const useServerOverviewData = () => {
    const configQuery = useServerInfo(serverId)
    const statusQuery = useServerStatus(serverId)
    const runtimeQuery = useServerRuntime(serverId, statusQuery.data)
    // Players data is included in runtime data
    
    return {
      config: configQuery,
      status: statusQuery,
      runtime: runtimeQuery,
      // players data available in runtime.onlinePlayers
      
      // 组合状态
      isLoading: configQuery.isLoading || statusQuery.isLoading,
      isError: configQuery.isError || statusQuery.isError,
      
      // 组合数据 (前端展示用)
      fullInfo: configQuery.data ? {
        ...configQuery.data,
        runtime: runtimeQuery.data
      } : undefined
    }
  }
  
  return { useServerOverviewData }
}

// Overview页面专用的组合查询
export const useOverviewPageQueries = () => {
  const { useServers, useSystemInfo } = useServerQueries()
  
  // 获取所有服务器配置
  const serverInfosQuery = useServers()
  const systemInfoQuery = useSystemInfo()
  
  // 为每个服务器获取状态和运行时信息
  const useAllServerStatuses = () => {
    const serverIds = serverInfosQuery.data?.map((s: ServerListItem) => s.id) || []
    
    return useQueries({
      queries: serverIds.map((id: string) => ({
        queryKey: queryKeys.serverStatuses.detail(id),
        queryFn: () => serverApi.getServerStatus(id),
        refetchInterval: 10000,
        staleTime: 5000,
      }))
    })
  }
  
  const useAllServerRuntimes = (statuses: Array<{ data?: ServerStatus }>) => {
    const serverIds = serverInfosQuery.data?.map((s: ServerListItem) => s.id) || []
    
    return useQueries({
      queries: serverIds.map((id: string, index: number) => {
        const status = statuses[index]?.data
        const isRunning = Boolean(status && ['RUNNING', 'STARTING', 'HEALTHY'].includes(status))
        
        return {
          queryKey: queryKeys.serverRuntimes.detail(id),
          queryFn: () => serverApi.getServerRuntime(id),
          enabled: isRunning,
          refetchInterval: isRunning ? 2000 : false,
          staleTime: 1000,
          retry: 1,
        } as const
      })
    })
  }
  
  return {
    serverInfosQuery,
    systemInfoQuery,
    useAllServerStatuses,
    useAllServerRuntimes
  }
}
