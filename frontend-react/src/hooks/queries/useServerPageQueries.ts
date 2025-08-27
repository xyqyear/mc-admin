import { serverApi } from '@/hooks/api/serverApi'
import { queryKeys } from '@/utils/api'
import { useQueries } from '@tanstack/react-query'
import { useServerQueries, useSystemQueries } from './useServerQueries'

export const useServerPageQueries = (serverId: string) => {
  const { useServerInfo, useServerStatus, useServerRuntime, useOnlinePlayers } = useServerQueries()
  
  // 服务器概览页面数据
  const useServerOverviewData = () => {
    const configQuery = useServerInfo(serverId)
    const statusQuery = useServerStatus(serverId)
    const runtimeQuery = useServerRuntime(serverId, statusQuery.data)
    const playersQuery = useOnlinePlayers(serverId, statusQuery.data)
    
    return {
      config: configQuery,
      status: statusQuery,
      runtime: runtimeQuery,
      players: playersQuery,
      
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
  const { useServerInfos } = useServerQueries()
  const { useSystemInfo } = useSystemQueries()
  
  // 获取所有服务器配置
  const serverInfosQuery = useServerInfos()
  const systemInfoQuery = useSystemInfo()
  
  // 为每个服务器获取状态和运行时信息
  const useAllServerStatuses = () => {
    const serverIds = serverInfosQuery.data?.map(s => s.id) || []
    
    return useQueries({
      queries: serverIds.map(id => ({
        queryKey: queryKeys.serverStatuses.detail(id),
        queryFn: () => serverApi.getServerStatus(id),
        refetchInterval: 10000,
        staleTime: 5000,
      }))
    })
  }
  
  const useAllServerRuntimes = (statuses: Array<{ data?: import('@/types/ServerInfo').ServerStatus }>) => {
    const serverIds = serverInfosQuery.data?.map(s => s.id) || []
    
    return useQueries({
      queries: serverIds.map((id, index) => {
        const status = statuses[index]?.data
        const isRunning = status && ['RUNNING', 'STARTING', 'HEALTHY'].includes(status)
        
        return {
          queryKey: queryKeys.serverRuntimes.detail(id),
          queryFn: () => serverApi.getServerRuntime(id),
          enabled: isRunning,
          refetchInterval: isRunning ? 2000 : false,
          staleTime: 1000,
          retry: 1,
        }
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
