import { serverApi, systemApi } from '@/hooks/api/serverApi'
import type { ServerInfo, ServerStatus } from '@/types/ServerInfo'
import type { ServerRuntime, SystemInfo } from '@/types/ServerRuntime'
import { queryKeys } from '@/utils/api'
import { useQuery, type UseQueryOptions } from '@tanstack/react-query'

export const useServerQueries = () => {
  // 服务器配置列表 (长缓存，5分钟)
  const useServerInfos = (options?: UseQueryOptions<ServerInfo[]>) => {
    return useQuery({
      queryKey: queryKeys.serverInfos.lists(),
      queryFn: serverApi.getServerInfos,
      staleTime: 5 * 60 * 1000, // 5分钟
      gcTime: 10 * 60 * 1000,   // 10分钟
      ...options
    })
  }
  
  // 单个服务器配置 (长缓存)
  const useServerInfo = (id: string, options?: UseQueryOptions<ServerInfo>) => {
    return useQuery({
      queryKey: queryKeys.serverInfos.detail(id),
      queryFn: () => serverApi.getServerInfo(id),
      enabled: !!id,
      staleTime: 5 * 60 * 1000,
      ...options
    })
  }
  
  // 服务器状态 (中等频率更新，10秒)
  const useServerStatus = (id: string, options?: UseQueryOptions<ServerStatus>) => {
    return useQuery({
      queryKey: queryKeys.serverStatuses.detail(id),
      queryFn: () => serverApi.getServerStatus(id),
      enabled: !!id,
      refetchInterval: 10000, // 10秒
      staleTime: 5000,        // 5秒
      ...options
    })
  }
  
  // 服务器运行时信息 (短缓存，仅运行状态时有效，2秒刷新)
  const useServerRuntime = (id: string, status?: ServerStatus, options?: UseQueryOptions<ServerRuntime>) => {
    const isRunning = status && ['RUNNING', 'STARTING', 'HEALTHY'].includes(status)
    
    return useQuery({
      queryKey: queryKeys.serverRuntimes.detail(id),
      queryFn: () => serverApi.getServerRuntime(id),
      enabled: !!id && isRunning,
      refetchInterval: isRunning ? 2000 : false, // 2秒刷新
      staleTime: 1000,                           // 1秒
      retry: 1, // 减少重试，避免无效请求
      ...options
    })
  }
  
  // 在线玩家 (仅健康状态时有效，5秒刷新)
  const useOnlinePlayers = (id: string, status?: ServerStatus, options?: UseQueryOptions<string[]>) => {
    const isHealthy = status === 'HEALTHY'
    
    return useQuery({
      queryKey: queryKeys.players.online(id),
      queryFn: () => serverApi.getOnlinePlayers(id),
      enabled: !!id && isHealthy,
      refetchInterval: isHealthy ? 5000 : false, // 5秒刷新
      staleTime: 2000,
      retry: 1,
      ...options
    })
  }
  
  // Compose文件内容 (长缓存)
  const useComposeFile = (id: string, options?: UseQueryOptions<string>) => {
    return useQuery({
      queryKey: queryKeys.compose.file(id),
      queryFn: () => serverApi.getComposeFile(id),
      enabled: !!id,
      staleTime: 10 * 60 * 1000, // 10分钟
      ...options
    })
  }
  
  return {
    useServerInfos,
    useServerInfo,
    useServerStatus,
    useServerRuntime,
    useOnlinePlayers,
    useComposeFile
  }
}

// 系统查询hooks
export const useSystemQueries = () => {
  const useSystemInfo = (options?: UseQueryOptions<SystemInfo>) => {
    return useQuery({
      queryKey: queryKeys.system.info(),
      queryFn: systemApi.getSystemInfo,
      refetchInterval: 5000, // 5秒刷新
      staleTime: 2000,       // 2秒
      ...options
    })
  }
  
  return {
    useSystemInfo
  }
}
