import type { ServerDiskUsageResponse } from '@/features/servers/contracts';
import { serverOnlinePlayersQueryOptions } from "@/features/players/queries";
import { serverCpuPercentQueryOptions, serverMemoryQueryOptions, serverDiskUsageQueryOptions, serverStatusesQueryOptions, useServerQueries } from "@/features/servers/queries";
import { useSnapshotQueries } from "@/features/backups/queries";
import { useSystemQueries } from "@/features/system/queries";
import type { ServerStatus } from "@/features/servers/contracts";
import { useQueries, useQuery } from "@tanstack/react-query";
import { useMemo } from "react";
// Batches per-server queries via useQueries to keep hook count stable as the
// server list grows; a single useQuery for statuses avoids dynamic-hook errors
// when the list shrinks.
export const useOverviewData = () => {
  const { useServers } = useServerQueries();
  const { useSystemInfo, useSystemCpuPercent, useSystemDiskUsage } = useSystemQueries();
  const { useBackupRepositoryUsage } = useSnapshotQueries();
  const serversQuery = useServers();
  const systemQuery = useSystemInfo();
  const systemCpuQuery = useSystemCpuPercent();
  const systemDiskQuery = useSystemDiskUsage();
  const backupRepositoryQuery = useBackupRepositoryUsage();
  const serversData = useMemo(() => serversQuery.data || [], [serversQuery.data]);
  const serverNum = serversData.length;
  const serverIds = useMemo(() => serversData.map((s) => s.id), [serversData]);
  const statusesQuery = useQuery(serverStatusesQueryOptions(serverIds));
  const serverStatuses = useMemo(() => statusesQuery.data || {}, [statusesQuery.data]);
  const runningServers = Object.values(serverStatuses).filter((status) => ["RUNNING", "STARTING", "HEALTHY"].includes(status)).length;
  // Player listing requires a fully started server; only HEALTHY qualifies.
  const healthyServerIds = useMemo(() => Object.entries(serverStatuses)
    .filter(([, status]) => status === "HEALTHY")
    .map(([id]) => id), [serverStatuses]);
  const playersQueries = useQueries({ queries: healthyServerIds.map((id) => serverOnlinePlayersQueryOptions(id)) });
  const runningServerIds = useMemo(() => Object.entries(serverStatuses)
    .filter(([, status]) => ["RUNNING", "STARTING", "HEALTHY"].includes(status))
    .map(([id]) => id), [serverStatuses]);
  const cpuQueries = useQueries({ queries: runningServerIds.map((id) => serverCpuPercentQueryOptions(id, serverStatuses[id])) });
  const memoryQueries = useQueries({ queries: runningServerIds.map((id) => serverMemoryQueryOptions(id, serverStatuses[id])) });
  const diskUsageQueries = useQueries({ queries: serverIds.map((id) => serverDiskUsageQueryOptions(id)) });
  const serverRuntimeData = useMemo(() => {
    const data: Record<string, {
      cpu?: {
        cpuPercentage: number;
      };
      memory?: {
        memoryUsageBytes: number;
      };
      players?: string[];
      diskUsage?: ServerDiskUsageResponse;
    }> = {};
    healthyServerIds.forEach((id, index) => {
      if (!data[id])
        data[id] = {};
      const onlinePlayers = playersQueries[index]?.data || [];
      data[id].players = onlinePlayers.map(player => player.current_name);
    });
    runningServerIds.forEach((id, index) => {
      if (!data[id])
        data[id] = {};
      data[id].cpu = cpuQueries[index]?.data;
    });
    runningServerIds.forEach((id, index) => {
      if (!data[id])
        data[id] = {};
      data[id].memory = memoryQueries[index]?.data;
    });
    serverIds.forEach((id, index) => {
      if (!data[id])
        data[id] = {};
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
  const onlinePlayerNum = useMemo(() => Object.values(serverRuntimeData).reduce((total, data) => total + (data.players?.length || 0), 0), [serverRuntimeData]);
  const enrichedServers = useMemo(() => serversData.map((server) => ({
    ...server,
    status: serverStatuses[server.id] || ("UNKNOWN" as ServerStatus),
    onlinePlayers: serverRuntimeData[server.id]?.players || [],
    cpuPercentage: serverRuntimeData[server.id]?.cpu?.cpuPercentage,
    memoryUsageBytes: serverRuntimeData[server.id]?.memory?.memoryUsageBytes,
    diskUsageBytes: serverRuntimeData[server.id]?.diskUsage?.diskUsageBytes,
    diskTotalBytes: serverRuntimeData[server.id]?.diskUsage?.diskTotalBytes,
    diskAvailableBytes: serverRuntimeData[server.id]?.diskUsage?.diskAvailableBytes,
  })), [serversData, serverStatuses, serverRuntimeData]);
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
    servers: serversData,
    enrichedServers,
    serverStatuses,
    systemInfo: systemQuery.data,
    systemCpuPercent: systemCpuQuery.data?.cpuPercentage,
    systemDiskUsage: systemDiskQuery.data,
    backupRepositoryUsage: backupRepositoryQuery.data,
    serverNum,
    runningServers,
    onlinePlayerNum,
    isLoading: serversQuery.isLoading || systemQuery.isLoading,
    isStatusLoading,
    isCpuLoading,
    isMemoryLoading,
    isPlayersLoading,
    isDiskLoading,
    isSystemCpuLoading: systemCpuQuery.isLoading,
    isSystemDiskLoading: systemDiskQuery.isLoading,
    isBackupRepositoryLoading: backupRepositoryQuery.isLoading,
    isError: serversQuery.isError || systemQuery.isError,
    isStatusError,
    isCpuError,
    isMemoryError,
    isPlayersError,
    isDiskError,
    isSystemCpuError: systemCpuQuery.isError,
    isSystemDiskError: systemDiskQuery.isError,
    isBackupRepositoryError: backupRepositoryQuery.isError,
    error: serversQuery.error || systemQuery.error,
    refetch: () => {
      serversQuery.refetch();
      systemQuery.refetch();
      systemCpuQuery.refetch();
      systemDiskQuery.refetch();
      backupRepositoryQuery.refetch();
      statusesQuery.refetch();
      cpuQueries.forEach((q) => q.refetch());
      memoryQueries.forEach((q) => q.refetch());
      playersQueries.forEach((q) => q.refetch());
      diskUsageQueries.forEach((q) => q.refetch());
    },
  };
};
