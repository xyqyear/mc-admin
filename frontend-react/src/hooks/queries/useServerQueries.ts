import { serverApi, systemApi, type ServerListItem } from '@/hooks/api/serverApi'
import type { ServerInfo, ServerStatus } from '@/types/ServerInfo'
import type { ServerRuntime, SystemInfo } from '@/types/ServerRuntime'
import { queryKeys } from '@/utils/api'
import { useQuery, type UseQueryOptions } from '@tanstack/react-query'

export const useServerQueries = () => {
  // 📈 新的综合服务器列表API - 一次获取所有服务器的基本信息、状态和运行时数据
  const useServers = (options?: UseQueryOptions<ServerListItem[]>) => {
    return useQuery({
      queryKey: queryKeys.servers(),
      queryFn: serverApi.getServers,
      staleTime: 30 * 1000,      // 30秒 - 平衡实时性和性能
      refetchInterval: 15 * 1000, // 15秒自动刷新 - 保持总览页面数据新鲜
      gcTime: 5 * 60 * 1000,      // 5分钟垃圾回收
      ...options
    })
  }

  // 单个服务器详细配置信息 (长缓存，用于详情页面)
  const useServerInfo = (id: string, options?: UseQueryOptions<ServerInfo>) => {
    return useQuery({
      queryKey: queryKeys.serverInfos.detail(id),
      queryFn: () => serverApi.getServerInfo(id),
      enabled: !!id,
      staleTime: 5 * 60 * 1000,   // 5分钟 - 配置信息变化较少
      gcTime: 10 * 60 * 1000,     // 10分钟
      ...options
    })
  }

  // 单个服务器状态 (快速更新，用于实时状态监控)
  const useServerStatus = (id: string, options?: UseQueryOptions<ServerStatus>) => {
    return useQuery({
      queryKey: queryKeys.serverStatuses.detail(id),
      queryFn: () => serverApi.getServerStatus(id),
      enabled: !!id,
      refetchInterval: 5000,      // 5秒 - 状态变化需要快速反应
      staleTime: 2000,            // 2秒
      ...options
    })
  }

  // 单个服务器运行时信息 (最快更新，仅运行状态时有效)
  const useServerRuntime = (id: string, status?: ServerStatus, options?: UseQueryOptions<ServerRuntime>) => {
    const isRunning = status && ['RUNNING', 'STARTING', 'HEALTHY'].includes(status)
    
    return useQuery({
      queryKey: queryKeys.serverRuntimes.detail(id),
      queryFn: () => serverApi.getServerRuntime(id),
      enabled: !!id && isRunning,
      refetchInterval: isRunning ? 3000 : false, // 3秒刷新运行时数据
      staleTime: 1000,                           // 1秒 - 运行时数据需要实时性
      retry: (failureCount, error: any) => {
        // 如果服务器停止运行，不要重试
        if (error?.response?.status === 409) return false
        return failureCount < 2
      },
      ...options
    })
  }

  // 系统信息 (中等频率更新)
  const useSystemInfo = (options?: UseQueryOptions<SystemInfo>) => {
    return useQuery({
      queryKey: queryKeys.system.info(),
      queryFn: systemApi.getSystemInfo,
      refetchInterval: 10000,     // 10秒刷新系统信息
      staleTime: 5000,           // 5秒
      ...options
    })
  }

  return {
    useServers,         // 🌟 新的主要API - 用于总览页面
    useServerInfo,      // 详细配置信息
    useServerStatus,    // 单个状态监控
    useServerRuntime,   // 单个运行时监控
    useSystemInfo,      // 系统信息
  }
}

// 🎯 总览页面专用的组合hooks
export const useOverviewData = () => {
  const { useServers, useSystemInfo } = useServerQueries()
  
  const serversQuery = useServers()
  const systemQuery = useSystemInfo()

  // 从服务器列表中提取统计数据
  const serversData = serversQuery.data || []
  const serverNum = serversData.length
  const runningServers = serversData.filter(s => 
    ['RUNNING', 'STARTING', 'HEALTHY'].includes(s.status)
  ).length
  const onlinePlayerNum = serversData.reduce((total, server) => 
    total + server.onlinePlayers.length, 0
  )

  return {
    // 原始数据
    servers: serversData,
    systemInfo: systemQuery.data,
    
    // 统计数据
    serverNum,
    runningServers,
    onlinePlayerNum,
    
    // 查询状态
    isLoading: serversQuery.isLoading || systemQuery.isLoading,
    isError: serversQuery.isError || systemQuery.isError,
    error: serversQuery.error || systemQuery.error,
    
    // 刷新方法
    refetch: () => {
      serversQuery.refetch()
      systemQuery.refetch()
    }
  }
}

// 🎯 服务器详情页面专用的组合hooks
export const useServerDetail = (id: string) => {
  const { useServerInfo, useServerStatus, useServerRuntime } = useServerQueries()
  
  const infoQuery = useServerInfo(id)
  const statusQuery = useServerStatus(id)
  const runtimeQuery = useServerRuntime(id, statusQuery.data)

  return {
    serverInfo: infoQuery.data,
    status: statusQuery.data,
    runtime: runtimeQuery.data,
    
    isLoading: infoQuery.isLoading || statusQuery.isLoading,
    isError: infoQuery.isError || statusQuery.isError,
    error: infoQuery.error || statusQuery.error,
    
    refetch: () => {
      infoQuery.refetch()
      statusQuery.refetch() 
      if (runtimeQuery.isEnabled) {
        runtimeQuery.refetch()
      }
    }
  }
}