import {
  serverApi,
  systemApi,
  type ServerIOStatsResponse,
  type ServerDiskUsageResponse,
  type ServerListItem,
} from "@/hooks/api/serverApi";
import type { ServerInfo, ServerStatus } from "@/types/ServerInfo";
import type { SystemInfo } from "@/types/ServerRuntime";
import { queryKeys } from "@/utils/api";
import { useQuery, useQueries, type UseQueryOptions } from "@tanstack/react-query";
import { useMemo } from "react";

export const useServerQueries = () => {
  // 📈 服务器基础信息列表 - 获取所有服务器的基本配置信息（不包含状态或运行时数据）
  const useServers = (options?: UseQueryOptions<ServerListItem[]>) => {
    return useQuery({
      queryKey: queryKeys.servers(),
      queryFn: serverApi.getServers,
      staleTime: 5 * 60 * 1000, // 5分钟 - 基础配置变化较少
      refetchInterval: false, // 不自动刷新，配置信息变化较少
      gcTime: 10 * 60 * 1000, // 10分钟垃圾回收
      ...options,
    });
  };

  // 单个服务器详细配置信息 (长缓存，用于详情页面)
  const useServerInfo = (id: string, options?: UseQueryOptions<ServerInfo>) => {
    return useQuery({
      queryKey: queryKeys.serverInfos.detail(id),
      queryFn: () => serverApi.getServerInfo(id),
      enabled: !!id,
      staleTime: 5 * 60 * 1000, // 5分钟 - 配置信息变化较少
      gcTime: 10 * 60 * 1000, // 10分钟
      ...options,
    });
  };

  // 单个服务器状态 (快速更新，用于实时状态监控)
  const useServerStatus = (
    id: string,
    options?: UseQueryOptions<ServerStatus>,
  ) => {
    return useQuery({
      queryKey: queryKeys.serverStatuses.detail(id),
      queryFn: () => serverApi.getServerStatus(id),
      enabled: !!id,
      refetchInterval: 5000, // 5秒 - 状态变化需要快速反应
      staleTime: 2000, // 2秒
      ...options,
    });
  };

  // 单个服务器系统资源 (CPU/内存，在RUNNING/STARTING/HEALTHY状态下可用)
  const useServerResources = (
    id: string,
    status?: ServerStatus,
    options?: UseQueryOptions<{
      cpuPercentage: number;
      memoryUsageBytes: number;
    }>,
  ) => {
    const resourcesAvailable =
      status && ["RUNNING", "STARTING", "HEALTHY"].includes(status);

    return useQuery({
      queryKey: [...queryKeys.serverRuntimes.detail(id), "resources"],
      queryFn: () => serverApi.getServerResources(id),
      enabled: !!id && resourcesAvailable,
      refetchInterval: resourcesAvailable ? 3000 : false, // 3秒刷新资源数据
      staleTime: 1000, // 1秒 - 资源数据需要实时性
      retry: (failureCount, error: any) => {
        // 如果服务器状态不支持资源监控，不要重试
        if (error?.response?.status === 409) return false;
        return failureCount < 2;
      },
      ...options,
    });
  };

  // 单个服务器玩家列表 (仅在HEALTHY状态下可用)
  const useServerPlayers = (
    id: string,
    status?: ServerStatus,
    options?: UseQueryOptions<string[]>,
  ) => {
    const playersAvailable = status === "HEALTHY";

    return useQuery({
      queryKey: [...queryKeys.players.online(id)],
      queryFn: () => serverApi.getServerPlayers(id),
      enabled: !!id && playersAvailable,
      refetchInterval: playersAvailable ? 5000 : false, // 5秒刷新玩家数据
      staleTime: 2000, // 2秒 - 玩家数据需要较好实时性
      retry: (failureCount, error: any) => {
        // 如果服务器不健康，不要重试
        if (error?.response?.status === 409) return false;
        return failureCount < 2;
      },
      ...options,
    });
  };

  // 单个服务器I/O统计 (在RUNNING/STARTING/HEALTHY状态下可用)
  const useServerIOStats = (
    id: string,
    status?: ServerStatus,
    options?: UseQueryOptions<ServerIOStatsResponse>,
  ) => {
    const iostatsAvailable =
      status && ["RUNNING", "STARTING", "HEALTHY"].includes(status);

    return useQuery({
      queryKey: [...queryKeys.serverRuntimes.detail(id), "iostats"],
      queryFn: () => serverApi.getServerIOStats(id),
      enabled: !!id && iostatsAvailable,
      refetchInterval: iostatsAvailable ? 5000 : false, // 5秒刷新I/O数据
      staleTime: 2000, // 2秒 - I/O数据需要较好实时性
      retry: (failureCount, error: any) => {
        // 如果服务器状态不支持I/O统计，不要重试
        if (error?.response?.status === 409) return false;
        return failureCount < 2;
      },
      ...options,
    });
  };

  // 单个服务器磁盘使用信息 (始终可用，不依赖运行状态)
  const useServerDiskUsage = (
    id: string,
    options?: UseQueryOptions<ServerDiskUsageResponse>,
  ) => {
    return useQuery({
      queryKey: [...queryKeys.serverRuntimes.detail(id), "disk"],
      queryFn: () => serverApi.getServerDiskUsage(id),
      enabled: !!id,
      refetchInterval: 30000, // 30秒刷新磁盘数据，频率较低
      staleTime: 15000, // 15秒 - 磁盘使用变化较慢
      retry: (failureCount, error: any) => {
        // 对于磁盘信息，只在服务器存在时重试
        if (error?.response?.status === 404) {
          return false;
        }
        return failureCount < 3;
      },
      ...options,
    });
  };

  // Compose文件内容 (长缓存，手动刷新)
  const useComposeFile = (id: string, options?: UseQueryOptions<string>) => {
    return useQuery({
      queryKey: queryKeys.compose.detail(id),
      queryFn: () => serverApi.getComposeFile(id),
      enabled: !!id,
      staleTime: 10 * 60 * 1000, // 10分钟 - Compose文件变化较少
      gcTime: 15 * 60 * 1000, // 15分钟
      retry: (failureCount, error: any) => {
        // 如果文件不存在，不要重试
        if (error?.response?.status === 404) return false;
        return failureCount < 2;
      },
      ...options,
    });
  };

  // 系统信息 (中等频率更新)
  const useSystemInfo = (options?: UseQueryOptions<SystemInfo>) => {
    return useQuery({
      queryKey: queryKeys.system.info(),
      queryFn: systemApi.getSystemInfo,
      refetchInterval: 10000, // 10秒刷新系统信息
      staleTime: 5000, // 5秒
      ...options,
    });
  };

  return {
    useServers, // 🌟 基础配置API - 用于获取服务器列表基本信息
    useServerInfo, // 详细配置信息
    useServerStatus, // 单个状态监控
    useServerResources, // 单个服务器系统资源 (CPU/内存)
    useServerPlayers, // 单个服务器玩家列表
    useServerIOStats, // 单个服务器I/O统计信息 (磁盘I/O和网络I/O，不包含磁盘空间)
    useServerDiskUsage, // 单个服务器磁盘使用信息 (磁盘空间，始终可用)
    useComposeFile, // Compose文件内容
    useSystemInfo, // 系统信息
  };
};

// 🎯 总览页面专用的组合hooks - 使用批量查询避免动态hooks问题
export const useOverviewData = () => {
  const { useServers, useSystemInfo } = useServerQueries();

  const serversQuery = useServers();
  const systemQuery = useSystemInfo();

  // 基础数据
  const serversData = serversQuery.data || [];
  const serverNum = serversData.length;
  
  // 使用稳定的服务器ID列表
  const serverIds = useMemo(() => serversData.map(s => s.id), [serversData]);

  // 批量获取所有服务器状态 - 使用单个查询避免动态hooks
  const statusesQuery = useQuery({
    queryKey: ['serverStatuses', 'batch', serverIds.sort()],
    queryFn: () => serverApi.getAllServerStatuses(serverIds),
    enabled: serverIds.length > 0,
    refetchInterval: 5000, // 5秒刷新状态
    staleTime: 2000, // 2秒
  });

  const serverStatuses = statusesQuery.data || {};

  // 计算运行中的服务器数量
  const runningServers = Object.values(serverStatuses).filter(status =>
    ["RUNNING", "STARTING", "HEALTHY"].includes(status)
  ).length;

  // 获取健康服务器的玩家数据 - 只为健康的服务器获取
  const healthyServerIds = useMemo(() => 
    Object.entries(serverStatuses)
      .filter(([_, status]) => status === "HEALTHY")
      .map(([id]) => id),
    [serverStatuses]
  );

  const playersQueries = useQueries({
    queries: healthyServerIds.map(id => ({
      queryKey: [...queryKeys.players.online(id)],
      queryFn: () => serverApi.getServerPlayers(id),
      refetchInterval: 5000, // 5秒刷新玩家数据
      staleTime: 2000,
      retry: (failureCount: number, error: any) => {
        if (error?.response?.status === 409) return false;
        return failureCount < 2;
      },
    }))
  });

  // 获取运行中服务器的资源数据
  const runningServerIds = useMemo(() =>
    Object.entries(serverStatuses)
      .filter(([_, status]) => ["RUNNING", "STARTING", "HEALTHY"].includes(status))
      .map(([id]) => id),
    [serverStatuses]
  );

  const resourcesQueries = useQueries({
    queries: runningServerIds.map(id => ({
      queryKey: [...queryKeys.serverRuntimes.detail(id), "resources"],
      queryFn: () => serverApi.getServerResources(id),
      refetchInterval: 3000, // 3秒刷新资源数据
      staleTime: 1000,
      retry: (failureCount: number, error: any) => {
        if (error?.response?.status === 409) return false;
        return failureCount < 2;
      },
    }))
  });

  // 获取所有服务器的磁盘使用情况
  const diskUsageQueries = useQueries({
    queries: serverIds.map(id => ({
      queryKey: [...queryKeys.serverRuntimes.detail(id), "disk"],
      queryFn: () => serverApi.getServerDiskUsage(id),
      refetchInterval: 30000, // 30秒刷新磁盘数据
      staleTime: 15000,
      retry: (failureCount: number, error: any) => {
        if (error?.response?.status === 404) return false;
        return failureCount < 3;
      },
    }))
  });

  // 构建运行时数据映射
  const serverRuntimeData = useMemo(() => {
    const data: Record<string, {
      resources?: { cpuPercentage: number; memoryUsageBytes: number };
      players?: string[];
      diskUsage?: { diskUsageBytes: number; diskTotalBytes: number; diskAvailableBytes: number };
    }> = {};

    // 收集玩家数据
    healthyServerIds.forEach((id, index) => {
      if (!data[id]) data[id] = {};
      data[id].players = playersQueries[index]?.data || [];
    });

    // 收集资源数据
    runningServerIds.forEach((id, index) => {
      if (!data[id]) data[id] = {};
      data[id].resources = resourcesQueries[index]?.data;
    });

    // 收集磁盘数据
    serverIds.forEach((id, index) => {
      if (!data[id]) data[id] = {};
      data[id].diskUsage = diskUsageQueries[index]?.data;
    });

    return data;
  }, [healthyServerIds, runningServerIds, serverIds, playersQueries, resourcesQueries, diskUsageQueries]);

  // 计算在线玩家总数
  const onlinePlayerNum = useMemo(() => 
    Object.values(serverRuntimeData).reduce(
      (total, data) => total + (data.players?.length || 0),
      0
    ),
    [serverRuntimeData]
  );

  // 构建完整的服务器数据（用于表格显示）
  const enrichedServers = useMemo(() => 
    serversData.map(server => ({
      ...server,
      status: serverStatuses[server.id] || 'UNKNOWN',
      onlinePlayers: serverRuntimeData[server.id]?.players || [],
      cpuPercentage: serverRuntimeData[server.id]?.resources?.cpuPercentage,
      memoryUsageBytes: serverRuntimeData[server.id]?.resources?.memoryUsageBytes,
      diskUsageBytes: serverRuntimeData[server.id]?.diskUsage?.diskUsageBytes,
      diskTotalBytes: serverRuntimeData[server.id]?.diskUsage?.diskTotalBytes,
      diskAvailableBytes: serverRuntimeData[server.id]?.diskUsage?.diskAvailableBytes,
    })),
    [serversData, serverStatuses, serverRuntimeData]
  );

  // 查询状态
  const isStatusLoading = statusesQuery.isLoading;
  const isResourcesLoading = resourcesQueries.some(q => q.isLoading);
  const isPlayersLoading = playersQueries.some(q => q.isLoading);
  const isDiskLoading = diskUsageQueries.some(q => q.isLoading);

  const isStatusError = statusesQuery.isError;
  const isResourcesError = resourcesQueries.some(q => q.isError);
  const isPlayersError = playersQueries.some(q => q.isError);
  const isDiskError = diskUsageQueries.some(q => q.isError);

  return {
    // 原始数据
    servers: serversData,
    enrichedServers, // 包含所有运行时数据的完整服务器列表
    serverStatuses,
    systemInfo: systemQuery.data,

    // 统计数据
    serverNum,
    runningServers,
    onlinePlayerNum,

    // 查询状态
    isLoading: serversQuery.isLoading || systemQuery.isLoading,
    isStatusLoading,
    isResourcesLoading,
    isPlayersLoading,
    isDiskLoading,
    isError: serversQuery.isError || systemQuery.isError,
    isStatusError,
    isResourcesError,
    isPlayersError,
    isDiskError,
    error: serversQuery.error || systemQuery.error,

    // 刷新方法
    refetch: () => {
      serversQuery.refetch();
      systemQuery.refetch();
      statusesQuery.refetch();
      resourcesQueries.forEach(q => q.refetch());
      playersQueries.forEach(q => q.refetch());
      diskUsageQueries.forEach(q => q.refetch());
    },
  };
};
