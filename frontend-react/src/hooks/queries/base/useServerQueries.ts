import {
  serverApi,
  type RestartScheduleResponse,
  type ServerDiskUsageResponse,
  type ServerIOStatsResponse,
  type ServerListItem,
} from "@/hooks/api/serverApi";
import type { ServerInfo, ServerStatus } from "@/types/ServerInfo";
import { queryKeys } from "@/utils/api";
import { useQuery, type UseQueryOptions } from "@tanstack/react-query";

export const useServerQueries = () => {
  const useServers = (options?: Omit<UseQueryOptions<ServerListItem[]>, 'queryKey' | 'queryFn'>) => {
    return useQuery({
      queryKey: queryKeys.servers(),
      queryFn: serverApi.getServers,
      staleTime: 5 * 60 * 1000,
      refetchInterval: false,
      gcTime: 10 * 60 * 1000,
      ...options,
    });
  };

  const useServerInfo = (id: string, options?: Omit<UseQueryOptions<ServerInfo>, 'queryKey' | 'queryFn'>) => {
    return useQuery({
      queryKey: queryKeys.serverInfos.detail(id),
      queryFn: () => serverApi.getServerInfo(id),
      enabled: !!id,
      staleTime: 5 * 60 * 1000,
      gcTime: 10 * 60 * 1000,
      ...options,
    });
  };

  const useServerStatus = (
    id: string,
    options?: Omit<UseQueryOptions<ServerStatus>, 'queryKey' | 'queryFn'>
  ) => {
    return useQuery({
      queryKey: queryKeys.serverStatuses.detail(id),
      queryFn: () => serverApi.getServerStatus(id),
      enabled: !!id,
      // Status drives many UI affordances; keep it fresh.
      refetchInterval: 5000,
      staleTime: 2000,
      ...options,
    });
  };

  // CPU/memory/I/O endpoints reject non-RUNNING/STARTING/HEALTHY states with 409.
  // Gate via `enabled` and skip retries on 409 so the query goes idle promptly
  // when the server stops.
  const useServerCpuPercent = (
    id: string,
    status?: ServerStatus,
    options?: Omit<UseQueryOptions<{
      cpuPercentage: number;
    }>, 'queryKey' | 'queryFn'>
  ) => {
    const resourcesAvailable =
      status && ["RUNNING", "STARTING", "HEALTHY"].includes(status);

    return useQuery({
      queryKey: queryKeys.serverRuntimes.cpu(id),
      queryFn: () => serverApi.getServerCpuPercent(id),
      enabled: !!id && resourcesAvailable,
      refetchInterval: resourcesAvailable ? 3000 : false,
      staleTime: 3000,
      retry: (failureCount, error: any) => {
        if (error?.response?.status === 409) return false;
        return failureCount < 2;
      },
      ...options,
    });
  };

  const useServerMemory = (
    id: string,
    status?: ServerStatus,
    options?: Omit<UseQueryOptions<{
      memoryUsageBytes: number;
    }>, 'queryKey' | 'queryFn'>
  ) => {
    const resourcesAvailable =
      status && ["RUNNING", "STARTING", "HEALTHY"].includes(status);

    return useQuery({
      queryKey: queryKeys.serverRuntimes.memory(id),
      queryFn: () => serverApi.getServerMemory(id),
      enabled: !!id && resourcesAvailable,
      refetchInterval: resourcesAvailable ? 3000 : false,
      staleTime: 1000,
      retry: (failureCount, error: any) => {
        if (error?.response?.status === 409) return false;
        return failureCount < 2;
      },
      ...options,
    });
  };

  const useServerIOStats = (
    id: string,
    status?: ServerStatus,
    options?: Omit<UseQueryOptions<ServerIOStatsResponse>, 'queryKey' | 'queryFn'>
  ) => {
    const iostatsAvailable =
      status && ["RUNNING", "STARTING", "HEALTHY"].includes(status);

    return useQuery({
      queryKey: queryKeys.serverRuntimes.ioStats(id),
      queryFn: () => serverApi.getServerIOStats(id),
      enabled: !!id && iostatsAvailable,
      refetchInterval: iostatsAvailable ? 5000 : false,
      staleTime: 2000,
      retry: (failureCount, error: any) => {
        if (error?.response?.status === 409) return false;
        return failureCount < 2;
      },
      ...options,
    });
  };

  // Disk usage is filesystem-level and remains available regardless of runtime state.
  const useServerDiskUsage = (
    id: string,
    options?: Omit<UseQueryOptions<ServerDiskUsageResponse>, 'queryKey' | 'queryFn'>
  ) => {
    return useQuery({
      queryKey: queryKeys.serverRuntimes.disk(id),
      queryFn: () => serverApi.getServerDiskUsage(id),
      enabled: !!id,
      refetchInterval: 30000,
      staleTime: 15000,
      retry: (failureCount, error: any) => {
        if (error?.response?.status === 404) {
          return false;
        }
        return failureCount < 3;
      },
      ...options,
    });
  };

  const useComposeFile = (id: string, options?: Omit<UseQueryOptions<string>, 'queryKey' | 'queryFn'>) => {
    return useQuery({
      queryKey: queryKeys.compose.detail(id),
      queryFn: () => serverApi.getComposeFile(id),
      enabled: !!id,
      staleTime: 10 * 60 * 1000,
      gcTime: 15 * 60 * 1000,
      retry: (failureCount, error: any) => {
        if (error?.response?.status === 404) return false;
        return failureCount < 2;
      },
      ...options,
    });
  };

  const useRestartSchedule = (
    id: string,
    options?: Omit<UseQueryOptions<RestartScheduleResponse | null>, 'queryKey' | 'queryFn'>
  ) => {
    return useQuery({
      queryKey: queryKeys.restartSchedule.detail(id),
      queryFn: () => serverApi.getRestartSchedule(id),
      enabled: !!id,
      staleTime: 2 * 60 * 1000,
      gcTime: 5 * 60 * 1000,
      retry: (failureCount, error: any) => {
        if (error?.response?.status === 404) return false;
        return failureCount < 2;
      },
      ...options,
    });
  };

  return {
    useServers,
    useServerInfo,
    useServerStatus,
    useServerCpuPercent,
    useServerMemory,
    useServerIOStats,
    useServerDiskUsage,
    useComposeFile,
    useRestartSchedule,
  };
};
