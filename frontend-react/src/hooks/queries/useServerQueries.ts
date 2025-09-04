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
import { useQuery, type UseQueryOptions } from "@tanstack/react-query";

export const useServerQueries = () => {
  // 📈 新的综合服务器列表API - 一次获取所有服务器的基本信息、状态和运行时数据
  const useServers = (options?: UseQueryOptions<ServerListItem[]>) => {
    return useQuery({
      queryKey: queryKeys.servers(),
      queryFn: serverApi.getServers,
      staleTime: 30 * 1000, // 30秒 - 平衡实时性和性能
      refetchInterval: 15 * 1000, // 15秒自动刷新 - 保持总览页面数据新鲜
      gcTime: 5 * 60 * 1000, // 5分钟垃圾回收
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
    useServers, // 🌟 主要API - 用于总览页面
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

// 🎯 总览页面专用的组合hooks
export const useOverviewData = () => {
  const { useServers, useSystemInfo } = useServerQueries();

  const serversQuery = useServers();
  const systemQuery = useSystemInfo();

  // 从服务器列表中提取统计数据
  const serversData = serversQuery.data || [];
  const serverNum = serversData.length;
  const runningServers = serversData.filter((s) =>
    ["RUNNING", "STARTING", "HEALTHY"].includes(s.status),
  ).length;
  const onlinePlayerNum = serversData.reduce(
    (total, server) => total + server.onlinePlayers.length,
    0,
  );

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
      serversQuery.refetch();
      systemQuery.refetch();
    },
  };
};
