import { useServerQueries } from "./useServerQueries";

/**
 * 服务器详情页面专用的组合查询hooks
 */
export const useServerDetailQueries = (serverId: string) => {
  const {
    useServerInfo,
    useServerStatus,
    useServerResources,
    useServerPlayers,
    useServerIOStats,
    useServerDiskUsage,
    useComposeFile,
  } = useServerQueries();

  // 服务器详情页面的主要数据 (使用分离API)
  const useServerDetailData = () => {
    // 基础配置信息 (长缓存)
    const configQuery = useServerInfo(serverId);

    // 服务器状态 (10秒刷新)
    const statusQuery = useServerStatus(serverId);

    // 系统资源信息 (3秒刷新，RUNNING/STARTING/HEALTHY时可用)
    const resourcesQuery = useServerResources(serverId, statusQuery.data);

    // 玩家列表 (5秒刷新，仅HEALTHY时可用)
    const playersQuery = useServerPlayers(serverId, statusQuery.data);

    // I/O统计信息 (5秒刷新，RUNNING/STARTING/HEALTHY时可用)
    const iostatsQuery = useServerIOStats(serverId, statusQuery.data);

    // 磁盘使用信息 (30秒刷新，始终可用)
    const diskUsageQuery = useServerDiskUsage(serverId);

    return {
      // 原始查询对象
      configQuery,
      statusQuery,
      resourcesQuery,
      playersQuery,
      iostatsQuery,
      diskUsageQuery,

      // 便捷的数据访问
      serverInfo: configQuery.data,
      status: statusQuery.data,
      resources: resourcesQuery.data,
      players: playersQuery.data || [],
      iostats: iostatsQuery.data,
      diskUsage: diskUsageQuery.data,

      // 组合状态
      isLoading: configQuery.isLoading || statusQuery.isLoading,
      isError: configQuery.isError || statusQuery.isError,
      error: configQuery.error || statusQuery.error,

      // 检查数据可用性
      hasServerInfo: !!configQuery.data,
      hasResourcesData: !!resourcesQuery.data,
      hasPlayersData: !!playersQuery.data?.length,
      hasIOStatsData: !!iostatsQuery.data,
      hasDiskUsageData: !!diskUsageQuery.data,

      // 状态判断
      isRunning:
        statusQuery.data &&
        ["RUNNING", "STARTING", "HEALTHY"].includes(statusQuery.data),
      isHealthy: statusQuery.data === "HEALTHY",

      // 组合数据对象 (用于传递给组件)
      serverData: configQuery.data
        ? {
            ...configQuery.data,
            status: statusQuery.data,
            resources: resourcesQuery.data,
            onlinePlayers: playersQuery.data || [],
            // 添加计算属性
            memoryUsagePercent:
              resourcesQuery.data && configQuery.data
                ? (resourcesQuery.data.memoryUsageBytes /
                    configQuery.data.maxMemoryBytes) *
                  100
                : 0,

            // 格式化的显示值
            displayMemoryUsage:
              resourcesQuery.data && configQuery.data
                ? `${(resourcesQuery.data.memoryUsageBytes / 1024 ** 3).toFixed(1)}GB / ${(configQuery.data.maxMemoryBytes / 1024 ** 3).toFixed(1)}GB`
                : "未知",

            displayCpuUsage: resourcesQuery.data
              ? `${resourcesQuery.data.cpuPercentage.toFixed(1)}%`
              : "未知",
          }
        : undefined,
    };
  };

  // Compose页面专用的数据查询
  const useServerComposeData = () => {
    // 服务器基本信息
    const serverInfoQuery = useServerInfo(serverId);

    // Compose文件内容
    const composeQuery = useComposeFile(serverId);

    return {
      // 查询对象
      serverInfoQuery,
      composeQuery,

      // 数据
      serverInfo: serverInfoQuery.data,
      composeContent: composeQuery.data,

      // 加载状态
      isLoading: serverInfoQuery.isLoading,
      serverLoading: serverInfoQuery.isLoading,

      // 错误状态
      isError: serverInfoQuery.isError,
      serverError: serverInfoQuery.isError,
      error: serverInfoQuery.error,
      serverErrorMessage: serverInfoQuery.error,

      // 数据可用性
      hasServerInfo: !!serverInfoQuery.data,

      // 刷新方法
      refetch: () => {
        serverInfoQuery.refetch();
        composeQuery.refetch();
      },
    };
  };

  return {
    useServerDetailData, // 使用新分离API的详情数据hook
    useServerComposeData, // Compose页面专用数据hook
  };
};
