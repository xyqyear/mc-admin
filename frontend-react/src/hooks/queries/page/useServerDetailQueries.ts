import { useServerQueries } from "@/hooks/queries/base/useServerQueries";

export const useServerDetailQueries = (serverId: string) => {
  const {
    useServerInfo,
    useServerStatus,
    useServerCpuPercent,
    useServerMemory,
    useServerIOStats,
    useServerDiskUsage,
    useComposeFile,
    useRestartSchedule,
  } = useServerQueries();

  const useServerDetailData = () => {
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

      isRunning:
        statusQuery.data &&
        ["RUNNING", "STARTING", "HEALTHY"].includes(statusQuery.data),
      isHealthy: statusQuery.data === "HEALTHY",

      serverData: configQuery.data
        ? {
          ...configQuery.data,
          status: statusQuery.data,
          cpu: cpuQuery.data,
          memory: memoryQuery.data,
          memoryUsagePercent:
            memoryQuery.data && configQuery.data
              ? (memoryQuery.data.memoryUsageBytes /
                configQuery.data.maxMemoryBytes) *
              100
              : 0,

          displayMemoryUsage:
            memoryQuery.data && configQuery.data
              ? `${(memoryQuery.data.memoryUsageBytes / 1024 ** 3).toFixed(
                1
              )}GB / ${(
                configQuery.data.maxMemoryBytes /
                1024 ** 3
              ).toFixed(1)}GB`
              : "未知",

          displayCpuUsage: cpuQuery.data
            ? `${cpuQuery.data.cpuPercentage.toFixed(1)}%`
            : "未知",
        }
        : undefined,
    };
  };

  const useServerComposeData = () => {
    const serverInfoQuery = useServerInfo(serverId);
    const composeQuery = useComposeFile(serverId);

    return {
      serverInfoQuery,
      composeQuery,

      serverInfo: serverInfoQuery.data,
      composeContent: composeQuery.data,

      isLoading: serverInfoQuery.isLoading,
      serverLoading: serverInfoQuery.isLoading,

      isError: serverInfoQuery.isError,
      serverError: serverInfoQuery.isError,
      error: serverInfoQuery.error,
      serverErrorMessage: serverInfoQuery.error,

      hasServerInfo: !!serverInfoQuery.data,

      refetch: () => {
        serverInfoQuery.refetch();
        composeQuery.refetch();
      },
    };
  };

  const useServerFilesData = () => {
    const serverInfoQuery = useServerInfo(serverId);

    return {
      serverInfoQuery,

      serverInfo: serverInfoQuery.data,

      isLoading: serverInfoQuery.isLoading,

      isError: serverInfoQuery.isError,
      error: serverInfoQuery.error,

      hasServerInfo: !!serverInfoQuery.data,

      refetch: () => {
        serverInfoQuery.refetch();
      },
    };
  };

  const useServerConsoleData = () => {
    const serverInfoQuery = useServerInfo(serverId);
    const statusQuery = useServerStatus(serverId);

    return {
      serverInfoQuery,
      statusQuery,

      serverInfo: serverInfoQuery.data,
      status: statusQuery.data,

      isLoading: serverInfoQuery.isLoading,

      isError: serverInfoQuery.isError,
      error: serverInfoQuery.error,

      hasServerInfo: !!serverInfoQuery.data,

      refetch: () => {
        serverInfoQuery.refetch();
        statusQuery.refetch();
      },
    };
  };

  return {
    useServerDetailData,
    useServerComposeData,
    useServerFilesData,
    useServerConsoleData,
  };
};
