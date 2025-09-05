import { serverApi, type ServerListItem } from "@/hooks/api/serverApi";
import type { ServerStatus } from "@/types/ServerInfo";
import { queryKeys } from "@/utils/api";
import { useQueries } from "@tanstack/react-query";
import { useServerQueries } from "./useServerQueries";

export const useServerPageQueries = (serverId: string) => {
  const {
    useServerInfo,
    useServerStatus,
    useServerCpuPercent,
    useServerMemory,
    useServerPlayers,
  } = useServerQueries();

  // 服务器概览页面数据 (使用分离API)
  const useServerOverviewData = () => {
    const configQuery = useServerInfo(serverId);
    const statusQuery = useServerStatus(serverId);
    const cpuQuery = useServerCpuPercent(serverId, statusQuery.data);
    const memoryQuery = useServerMemory(serverId, statusQuery.data);
    const playersQuery = useServerPlayers(serverId, statusQuery.data);

    return {
      config: configQuery,
      status: statusQuery,
      cpu: cpuQuery,
      memory: memoryQuery,
      players: playersQuery,

      // 组合状态
      isLoading: configQuery.isLoading || statusQuery.isLoading,
      isError: configQuery.isError || statusQuery.isError,

      // 组合数据 (前端展示用)
      fullInfo: configQuery.data
        ? {
            ...configQuery.data,
            cpu: cpuQuery.data,
            memory: memoryQuery.data,
            onlinePlayers: playersQuery.data || [],
          }
        : undefined,
    };
  };

  return { useServerOverviewData };
};

// Overview页面专用的组合查询
export const useOverviewPageQueries = () => {
  const { useServers, useSystemInfo } = useServerQueries();

  // 获取所有服务器配置
  const serverInfosQuery = useServers();
  const systemInfoQuery = useSystemInfo();

  // 为每个服务器获取状态和运行时信息
  const useAllServerStatuses = () => {
    const serverIds =
      serverInfosQuery.data?.map((s: ServerListItem) => s.id) || [];

    return useQueries({
      queries: serverIds.map((id: string) => ({
        queryKey: queryKeys.serverStatuses.detail(id),
        queryFn: () => serverApi.getServerStatus(id),
        refetchInterval: 10000,
        staleTime: 5000,
      })),
    });
  };

  const useAllServerCpuPercent = (statuses: Array<{ data?: ServerStatus }>) => {
    const serverIds =
      serverInfosQuery.data?.map((s: ServerListItem) => s.id) || [];

    return useQueries({
      queries: serverIds.map((id: string, index: number) => {
        const status = statuses[index]?.data;
        const isRunning = Boolean(
          status && ["RUNNING", "STARTING", "HEALTHY"].includes(status)
        );

        return {
          queryKey: [...queryKeys.serverRuntimes.detail(id), "cpu"],
          queryFn: () => serverApi.getServerCpuPercent(id),
          enabled: isRunning,
          refetchInterval: isRunning ? 5000 : false, // 5秒刷新CPU（较慢）
          staleTime: 2000,
          retry: 1,
        } as const;
      }),
    });
  };

  const useAllServerMemory = (statuses: Array<{ data?: ServerStatus }>) => {
    const serverIds =
      serverInfosQuery.data?.map((s: ServerListItem) => s.id) || [];

    return useQueries({
      queries: serverIds.map((id: string, index: number) => {
        const status = statuses[index]?.data;
        const isRunning = Boolean(
          status && ["RUNNING", "STARTING", "HEALTHY"].includes(status)
        );

        return {
          queryKey: [...queryKeys.serverRuntimes.detail(id), "memory"],
          queryFn: () => serverApi.getServerMemory(id),
          enabled: isRunning,
          refetchInterval: isRunning ? 3000 : false, // 3秒刷新内存（较快）
          staleTime: 1000,
          retry: 1,
        } as const;
      }),
    });
  };

  const useAllServerPlayers = (statuses: Array<{ data?: ServerStatus }>) => {
    const serverIds =
      serverInfosQuery.data?.map((s: ServerListItem) => s.id) || [];

    return useQueries({
      queries: serverIds.map((id: string, index: number) => {
        const status = statuses[index]?.data;
        const isHealthy = Boolean(status === "HEALTHY");

        return {
          queryKey: [...queryKeys.players.online(id)],
          queryFn: () => serverApi.getServerPlayers(id),
          enabled: isHealthy,
          refetchInterval: isHealthy ? 5000 : false,
          staleTime: 2000,
          retry: 1,
        } as const;
      }),
    });
  };

  return {
    serverInfosQuery,
    systemInfoQuery,
    useAllServerStatuses,
    useAllServerCpuPercent,
    useAllServerMemory,
    useAllServerPlayers,
  };
};
