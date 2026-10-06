import { queryOptions } from '@tanstack/react-query';
import { shouldRetryQuery } from '@/shared/http/api';
import { serverApi } from "@/features/servers/api";
import type { ServerStatus } from "@/features/servers/contracts";
import { queryKeys } from "@/shared/http/api";
import { useQuery } from "@tanstack/react-query";
export const useServers = (options?: Partial<Omit<ReturnType<typeof serversQueryOptions>, 'queryKey' | 'queryFn'>>) => {
  return useQuery({ ...serversQueryOptions(), ...options });
};

export const useServerInfo = (id: string, options?: Partial<Omit<ReturnType<typeof serverInfoQueryOptions>, 'queryKey' | 'queryFn'>>) => {
  return useQuery({ ...serverInfoQueryOptions(id), ...options });
};

export const useServerStatus = (id: string, options?: Partial<Omit<ReturnType<typeof serverStatusQueryOptions>, 'queryKey' | 'queryFn'>>) => {
  return useQuery({ ...serverStatusQueryOptions(id), ...options });
};

export const useServerMaintenance = (id: string, options?: Partial<Omit<ReturnType<typeof serverMaintenanceQueryOptions>, 'queryKey' | 'queryFn'>>) => useQuery({ ...serverMaintenanceQueryOptions(id), ...options });

export const useServerCpuPercent = (id: string, status?: ServerStatus, options?: Partial<Omit<ReturnType<typeof serverCpuPercentQueryOptions>, 'queryKey' | 'queryFn'>>) => {
  return useQuery({ ...serverCpuPercentQueryOptions(id, status), ...options });
};

export const useServerMemory = (id: string, status?: ServerStatus, options?: Partial<Omit<ReturnType<typeof serverMemoryQueryOptions>, 'queryKey' | 'queryFn'>>) => {
  return useQuery({ ...serverMemoryQueryOptions(id, status), ...options });
};

export const useServerIOStats = (id: string, status?: ServerStatus, options?: Partial<Omit<ReturnType<typeof serverIOStatsQueryOptions>, 'queryKey' | 'queryFn'>>) => {
  return useQuery({ ...serverIOStatsQueryOptions(id, status), ...options });
};

export const useServerDiskUsage = (id: string, options?: Partial<Omit<ReturnType<typeof serverDiskUsageQueryOptions>, 'queryKey' | 'queryFn'>>) => {
  return useQuery({ ...serverDiskUsageQueryOptions(id), ...options });
};

export const useRestartSchedule = (id: string, options?: Partial<Omit<ReturnType<typeof restartScheduleQueryOptions>, 'queryKey' | 'queryFn'>>) => {
  return useQuery({ ...restartScheduleQueryOptions(id), ...options });
};

export const serversQueryOptions = () => {
  return queryOptions({
    queryKey: queryKeys.servers(),
    queryFn: serverApi.getServers,
    staleTime: 5 * 60 * 1000,
    refetchInterval: false,
    gcTime: 10 * 60 * 1000
  });
};
export const serverInfoQueryOptions = (id: string) => {
  return queryOptions({
    queryKey: queryKeys.serverInfos.detail(id),
    queryFn: () => serverApi.getServerInfo(id),
    enabled: !!id,
    staleTime: 5 * 60 * 1000,
    gcTime: 10 * 60 * 1000
  });
};
export const serverStatusQueryOptions = (id: string) => {
  return queryOptions({
    queryKey: queryKeys.serverStatuses.detail(id),
    queryFn: () => serverApi.getServerStatus(id),
    enabled: !!id,
    refetchInterval: 5000,
    staleTime: 2000
  });
};
export const serverMaintenanceQueryOptions = (id: string) => {
  return queryOptions({
    queryKey: queryKeys.serverMaintenance.detail(id),
    queryFn: () => serverApi.getServerMaintenance(id),
    enabled: !!id,
    refetchInterval: 1000
  });
};
export const serverCpuPercentQueryOptions = (id: string, status?: ServerStatus) => {
  const resourcesAvailable = !!status && ["RUNNING", "STARTING", "HEALTHY"].includes(status);
  return queryOptions({
    queryKey: queryKeys.serverRuntimes.cpu(id),
    queryFn: () => serverApi.getServerCpuPercent(id),
    enabled: !!id && resourcesAvailable,
    refetchInterval: resourcesAvailable ? 3000 : false,
    staleTime: 3000,
    retry: (failureCount, error) => shouldRetryQuery(failureCount, error, 2)
  });
};
export const serverMemoryQueryOptions = (id: string, status?: ServerStatus) => {
  const resourcesAvailable = !!status && ["RUNNING", "STARTING", "HEALTHY"].includes(status);
  return queryOptions({
    queryKey: queryKeys.serverRuntimes.memory(id),
    queryFn: () => serverApi.getServerMemory(id),
    enabled: !!id && resourcesAvailable,
    refetchInterval: resourcesAvailable ? 3000 : false,
    staleTime: 1000,
    retry: (failureCount, error) => shouldRetryQuery(failureCount, error, 2)
  });
};
export const serverIOStatsQueryOptions = (id: string, status?: ServerStatus) => {
  const iostatsAvailable = !!status && ["RUNNING", "STARTING", "HEALTHY"].includes(status);
  return queryOptions({
    queryKey: queryKeys.serverRuntimes.ioStats(id),
    queryFn: () => serverApi.getServerIOStats(id),
    enabled: !!id && iostatsAvailable,
    refetchInterval: iostatsAvailable ? 5000 : false,
    staleTime: 2000,
    retry: (failureCount, error) => shouldRetryQuery(failureCount, error, 2)
  });
};
export const serverDiskUsageQueryOptions = (id: string) => {
  return queryOptions({
    queryKey: queryKeys.serverRuntimes.disk(id),
    queryFn: () => serverApi.getServerDiskUsage(id),
    enabled: !!id,
    refetchInterval: 30000,
    staleTime: 15000,
    retry: (failureCount, error) => shouldRetryQuery(failureCount, error, 3)
  });
};
export const restartScheduleQueryOptions = (id: string) => {
  return queryOptions({
    queryKey: queryKeys.restartSchedule.detail(id),
    queryFn: () => serverApi.getRestartSchedule(id),
    enabled: !!id,
    staleTime: 2 * 60 * 1000,
    gcTime: 5 * 60 * 1000,
    retry: (failureCount, error) => shouldRetryQuery(failureCount, error, 2)
  });
};
export const serverStatusesQueryOptions = (ids: string[]) => {
  const sortedIds = [...ids].sort();
  return queryOptions({ queryKey: queryKeys.serverStatuses.batch(sortedIds), queryFn: () => serverApi.getAllServerStatuses(sortedIds), enabled: sortedIds.length > 0, refetchInterval: 5000, staleTime: 2000 });
};
