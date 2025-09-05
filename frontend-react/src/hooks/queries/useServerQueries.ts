import {
  serverApi,
  systemApi,
  type ServerDiskUsageResponse,
  type ServerIOStatsResponse,
  type ServerListItem,
} from "@/hooks/api/serverApi";
import type { ServerInfo, ServerStatus } from "@/types/ServerInfo";
import type { SystemInfo } from "@/types/ServerRuntime";
import { queryKeys } from "@/utils/api";
import { useQuery, type UseQueryOptions } from "@tanstack/react-query";

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
    options?: UseQueryOptions<ServerStatus>
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

  // 单个服务器CPU百分比 (在RUNNING/STARTING/HEALTHY状态下可用)
  const useServerCpuPercent = (
    id: string,
    status?: ServerStatus,
    options?: UseQueryOptions<{
      cpuPercentage: number;
    }>
  ) => {
    const resourcesAvailable =
      status && ["RUNNING", "STARTING", "HEALTHY"].includes(status);

    return useQuery({
      queryKey: [...queryKeys.serverRuntimes.detail(id), "cpu"],
      queryFn: () => serverApi.getServerCpuPercent(id),
      enabled: !!id && resourcesAvailable,
      refetchInterval: resourcesAvailable ? 3000 : false, // 3秒刷新CPU数据
      staleTime: 3000, // 3秒
      retry: (failureCount, error: any) => {
        // 如果服务器状态不支持CPU监控，不要重试
        if (error?.response?.status === 409) return false;
        return failureCount < 2;
      },
      ...options,
    });
  };

  // 单个服务器内存使用量 (在RUNNING/STARTING/HEALTHY状态下可用)
  const useServerMemory = (
    id: string,
    status?: ServerStatus,
    options?: UseQueryOptions<{
      memoryUsageBytes: number;
    }>
  ) => {
    const resourcesAvailable =
      status && ["RUNNING", "STARTING", "HEALTHY"].includes(status);

    return useQuery({
      queryKey: [...queryKeys.serverRuntimes.detail(id), "memory"],
      queryFn: () => serverApi.getServerMemory(id),
      enabled: !!id && resourcesAvailable,
      refetchInterval: resourcesAvailable ? 3000 : false, // 3秒刷新内存数据（较快）
      staleTime: 1000, // 1秒 - 内存数据需要实时性
      retry: (failureCount, error: any) => {
        // 如果服务器状态不支持内存监控，不要重试
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
    options?: UseQueryOptions<string[]>
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
    options?: UseQueryOptions<ServerIOStatsResponse>
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
    options?: UseQueryOptions<ServerDiskUsageResponse>
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

  // 系统信息 (中等频率更新，不包含CPU百分比)
  const useSystemInfo = (options?: UseQueryOptions<SystemInfo>) => {
    return useQuery({
      queryKey: queryKeys.system.info(),
      queryFn: systemApi.getSystemInfo,
      refetchInterval: 10000, // 10秒刷新系统信息
      staleTime: 5000, // 5秒
      ...options,
    });
  };

  // 系统CPU百分比 (较慢更新，因为需要1-2秒计算时间)
  const useSystemCpuPercent = (
    options?: UseQueryOptions<{ cpuPercentage: number }>
  ) => {
    return useQuery({
      queryKey: [...queryKeys.system.info(), "cpu"],
      queryFn: systemApi.getSystemCpuPercent,
      refetchInterval: 3000, // 3秒刷新CPU百分比（比其他系统信息慢）
      staleTime: 3000, // 3秒
      ...options,
    });
  };

  return {
    useServers, // 🌟 基础配置API - 用于获取服务器列表基本信息
    useServerInfo, // 详细配置信息
    useServerStatus, // 单个状态监控
    useServerCpuPercent, // 单个服务器CPU百分比 (分离后的接口)
    useServerMemory, // 单个服务器内存使用量 (分离后的接口)
    useServerPlayers, // 单个服务器玩家列表
    useServerIOStats, // 单个服务器I/O统计信息 (磁盘I/O和网络I/O，不包含磁盘空间)
    useServerDiskUsage, // 单个服务器磁盘使用信息 (磁盘空间，始终可用)
    useComposeFile, // Compose文件内容
    useSystemInfo, // 系统信息 (不包含CPU百分比)
    useSystemCpuPercent, // 系统CPU百分比 (分离后的接口)
  };
};
