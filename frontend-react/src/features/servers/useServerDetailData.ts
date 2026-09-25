import { useServerQueries } from "@/features/servers/queries";
export const useServerDetailData = (serverId: string) => {
  const { useServerInfo, useServerStatus, useServerCpuPercent, useServerMemory, useServerIOStats, useServerDiskUsage, useRestartSchedule, } = useServerQueries();
  const configQuery = useServerInfo(serverId);
  const statusQuery = useServerStatus(serverId);
  const cpuQuery = useServerCpuPercent(serverId, statusQuery.data);
  const memoryQuery = useServerMemory(serverId, statusQuery.data);
  const iostatsQuery = useServerIOStats(serverId, statusQuery.data);
  const diskUsageQuery = useServerDiskUsage(serverId);
  const restartScheduleQuery = useRestartSchedule(serverId);
  return {
    configQuery,
    statusQuery,
    cpuQuery,
    memoryQuery,
    iostatsQuery,
    diskUsageQuery,
    restartScheduleQuery,
    serverInfo: configQuery.data,
    status: statusQuery.data,
    cpu: cpuQuery.data,
    memory: memoryQuery.data,
    iostats: iostatsQuery.data,
    diskUsage: diskUsageQuery.data,
    restartSchedule: restartScheduleQuery.data,
    isLoading: configQuery.isLoading || statusQuery.isLoading,
    isError: configQuery.isError || statusQuery.isError,
    error: configQuery.error || statusQuery.error,
    hasServerInfo: !!configQuery.data,
    hasCpuData: !!cpuQuery.data,
    hasMemoryData: !!memoryQuery.data,
    hasIOStatsData: !!iostatsQuery.data,
    hasDiskUsageData: !!diskUsageQuery.data,
    hasRestartScheduleData: !!restartScheduleQuery.data,
    isRunning: statusQuery.data &&
      ["RUNNING", "STARTING", "HEALTHY"].includes(statusQuery.data),
    isHealthy: statusQuery.data === "HEALTHY",
    serverData: configQuery.data
      ? {
        ...configQuery.data,
        status: statusQuery.data,
        cpu: cpuQuery.data,
        memory: memoryQuery.data,
        memoryUsagePercent: memoryQuery.data && configQuery.data
          ? (memoryQuery.data.memoryUsageBytes /
            configQuery.data.maxMemoryBytes) *
            100
          : 0,
        displayMemoryUsage: memoryQuery.data && configQuery.data
          ? `${(memoryQuery.data.memoryUsageBytes / 1024 ** 3).toFixed(1)}GB / ${(configQuery.data.maxMemoryBytes /
            1024 ** 3).toFixed(1)}GB`
          : "未知",
        displayCpuUsage: cpuQuery.data
          ? `${cpuQuery.data.cpuPercentage.toFixed(1)}%`
          : "未知",
      }
      : undefined,
  };
};
