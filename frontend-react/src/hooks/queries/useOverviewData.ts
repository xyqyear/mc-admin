import { serverApi, type ServerDiskUsageResponse } from "@/hooks/api/serverApi";
import type { ServerStatus } from "@/types/ServerInfo";
import { queryKeys } from "@/utils/api";
import { useQueries, useQuery } from "@tanstack/react-query";
import { useMemo } from "react";
import { useServerQueries } from "./useServerQueries";

// 🎯 总览页面专用的组合hooks - 使用批量查询避免动态hooks问题
export const useOverviewData = () => {
  const { useServers, useSystemInfo, useSystemCpuPercent } = useServerQueries();

  const serversQuery = useServers();
  const systemQuery = useSystemInfo();
  const systemCpuQuery = useSystemCpuPercent();

  // 基础数据
  const serversData = serversQuery.data || [];
  const serverNum = serversData.length;

  // 使用稳定的服务器ID列表
  const serverIds = useMemo(() => serversData.map((s) => s.id), [serversData]);

  // 批量获取所有服务器状态 - 使用单个查询避免动态hooks
  const statusesQuery = useQuery({
    queryKey: ["serverStatuses", "batch", serverIds.sort()],
    queryFn: () => serverApi.getAllServerStatuses(serverIds),
    enabled: serverIds.length > 0,
    refetchInterval: 5000, // 5秒刷新状态
    staleTime: 2000, // 2秒
  });

  const serverStatuses = statusesQuery.data || {};

  // 计算运行中的服务器数量
  const runningServers = Object.values(serverStatuses).filter((status) =>
    ["RUNNING", "STARTING", "HEALTHY"].includes(status)
  ).length;

  // 获取健康服务器的玩家数据 - 只为健康的服务器获取
  const healthyServerIds = useMemo(
    () =>
      Object.entries(serverStatuses)
        .filter(([_, status]) => status === "HEALTHY")
        .map(([id]) => id),
    [serverStatuses]
  );

  const playersQueries = useQueries({
    queries: healthyServerIds.map((id) => ({
      queryKey: [...queryKeys.players.online(id)],
      queryFn: () => serverApi.getServerPlayers(id),
      refetchInterval: 5000, // 5秒刷新玩家数据
      staleTime: 2000,
      retry: (failureCount: number, error: any) => {
        if (error?.response?.status === 409) return false;
        return failureCount < 2;
      },
    })),
  });

  // 获取运行中服务器的资源数据
  const runningServerIds = useMemo(
    () =>
      Object.entries(serverStatuses)
        .filter(([_, status]) =>
          ["RUNNING", "STARTING", "HEALTHY"].includes(status)
        )
        .map(([id]) => id),
    [serverStatuses]
  );

  // 获取运行中服务器的CPU数据
  const cpuQueries = useQueries({
    queries: runningServerIds.map((id) => ({
      queryKey: [...queryKeys.serverRuntimes.detail(id), "cpu"],
      queryFn: () => serverApi.getServerCpuPercent(id),
      refetchInterval: 5000, // 5秒刷新CPU数据（较慢）
      staleTime: 2000,
      retry: (failureCount: number, error: any) => {
        if (error?.response?.status === 409) return false;
        return failureCount < 2;
      },
    })),
  });

  // 获取运行中服务器的内存数据
  const memoryQueries = useQueries({
    queries: runningServerIds.map((id) => ({
      queryKey: [...queryKeys.serverRuntimes.detail(id), "memory"],
      queryFn: () => serverApi.getServerMemory(id),
      refetchInterval: 3000, // 3秒刷新内存数据（较快）
      staleTime: 1000,
      retry: (failureCount: number, error: any) => {
        if (error?.response?.status === 409) return false;
        return failureCount < 2;
      },
    })),
  });

  // 获取所有服务器的磁盘使用情况
  const diskUsageQueries = useQueries({
    queries: serverIds.map((id) => ({
      queryKey: [...queryKeys.serverRuntimes.detail(id), "disk"],
      queryFn: () => serverApi.getServerDiskUsage(id),
      refetchInterval: 30000, // 30秒刷新磁盘数据
      staleTime: 15000,
      retry: (failureCount: number, error: any) => {
        if (error?.response?.status === 404) return false;
        return failureCount < 3;
      },
    })),
  });

  // 构建运行时数据映射
  const serverRuntimeData = useMemo(() => {
    const data: Record<
      string,
      {
        cpu?: { cpuPercentage: number };
        memory?: { memoryUsageBytes: number };
        players?: string[];
        diskUsage?: ServerDiskUsageResponse;
      }
    > = {};

    // 收集玩家数据
    healthyServerIds.forEach((id, index) => {
      if (!data[id]) data[id] = {};
      data[id].players = playersQueries[index]?.data || [];
    });

    // 收集CPU数据
    runningServerIds.forEach((id, index) => {
      if (!data[id]) data[id] = {};
      data[id].cpu = cpuQueries[index]?.data;
    });

    // 收集内存数据
    runningServerIds.forEach((id, index) => {
      if (!data[id]) data[id] = {};
      data[id].memory = memoryQueries[index]?.data;
    });

    // 收集磁盘数据
    serverIds.forEach((id, index) => {
      if (!data[id]) data[id] = {};
      data[id].diskUsage = diskUsageQueries[index]?.data;
    });

    return data;
  }, [
    healthyServerIds,
    runningServerIds,
    serverIds,
    playersQueries,
    cpuQueries,
    memoryQueries,
    diskUsageQueries,
  ]);

  // 计算在线玩家总数
  const onlinePlayerNum = useMemo(
    () =>
      Object.values(serverRuntimeData).reduce(
        (total, data) => total + (data.players?.length || 0),
        0
      ),
    [serverRuntimeData]
  );

  // 构建完整的服务器数据（用于表格显示）
  const enrichedServers = useMemo(
    () =>
      serversData.map((server) => ({
        ...server,
        status: serverStatuses[server.id] || ("UNKNOWN" as ServerStatus),
        onlinePlayers: serverRuntimeData[server.id]?.players || [],
        cpuPercentage: serverRuntimeData[server.id]?.cpu?.cpuPercentage,
        memoryUsageBytes:
          serverRuntimeData[server.id]?.memory?.memoryUsageBytes,
        diskUsageBytes: serverRuntimeData[server.id]?.diskUsage?.diskUsageBytes,
        diskTotalBytes: serverRuntimeData[server.id]?.diskUsage?.diskTotalBytes,
        diskAvailableBytes:
          serverRuntimeData[server.id]?.diskUsage?.diskAvailableBytes,
      })),
    [serversData, serverStatuses, serverRuntimeData]
  );

  // 查询状态
  const isStatusLoading = statusesQuery.isLoading;
  const isCpuLoading = cpuQueries.some((q) => q.isLoading);
  const isMemoryLoading = memoryQueries.some((q) => q.isLoading);
  const isPlayersLoading = playersQueries.some((q) => q.isLoading);
  const isDiskLoading = diskUsageQueries.some((q) => q.isLoading);

  const isStatusError = statusesQuery.isError;
  const isCpuError = cpuQueries.some((q) => q.isError);
  const isMemoryError = memoryQueries.some((q) => q.isError);
  const isPlayersError = playersQueries.some((q) => q.isError);
  const isDiskError = diskUsageQueries.some((q) => q.isError);

  return {
    // 原始数据
    servers: serversData,
    enrichedServers, // 包含所有运行时数据的完整服务器列表
    serverStatuses,
    systemInfo: systemQuery.data,
    systemCpuPercent: systemCpuQuery.data?.cpuPercentage,

    // 统计数据
    serverNum,
    runningServers,
    onlinePlayerNum,

    // 查询状态
    isLoading: serversQuery.isLoading || systemQuery.isLoading,
    isStatusLoading,
    isCpuLoading,
    isMemoryLoading,
    isPlayersLoading,
    isDiskLoading,
    isSystemCpuLoading: systemCpuQuery.isLoading,
    isError: serversQuery.isError || systemQuery.isError,
    isStatusError,
    isCpuError,
    isMemoryError,
    isPlayersError,
    isDiskError,
    isSystemCpuError: systemCpuQuery.isError,
    error: serversQuery.error || systemQuery.error,

    // 刷新方法
    refetch: () => {
      serversQuery.refetch();
      systemQuery.refetch();
      systemCpuQuery.refetch();
      statusesQuery.refetch();
      cpuQueries.forEach((q) => q.refetch());
      memoryQueries.forEach((q) => q.refetch());
      playersQueries.forEach((q) => q.refetch());
      diskUsageQueries.forEach((q) => q.refetch());
    },
  };
};
