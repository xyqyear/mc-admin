import { useServerQueries } from './useServerQueries'

/**
 * 服务器详情页面专用的组合查询hooks
 */
export const useServerDetailQueries = (serverId: string) => {
  const { 
    useServerInfo, 
    useServerStatus, 
    useServerRuntime, 
    useOnlinePlayers 
  } = useServerQueries()
  
  // 服务器详情页面的主要数据
  const useServerDetailData = () => {
    // 基础配置信息 (长缓存)
    const configQuery = useServerInfo(serverId)
    
    // 服务器状态 (10秒刷新) 
    const statusQuery = useServerStatus(serverId)
    
    // 运行时信息 (依赖状态，2秒刷新)
    const runtimeQuery = useServerRuntime(serverId, statusQuery.data)
    
    // 在线玩家信息 (依赖状态，5秒刷新)
    const playersQuery = useOnlinePlayers(serverId, statusQuery.data)
    
    return {
      // 原始查询对象
      configQuery,
      statusQuery, 
      runtimeQuery,
      playersQuery,
      
      // 便捷的数据访问
      serverInfo: configQuery.data,
      status: statusQuery.data,
      runtime: runtimeQuery.data,
      players: playersQuery.data,
      
      // 组合状态
      isLoading: configQuery.isLoading || statusQuery.isLoading,
      isError: configQuery.isError || statusQuery.isError,
      error: configQuery.error || statusQuery.error,
      
      // 检查数据可用性
      hasServerInfo: !!configQuery.data,
      hasRuntimeData: !!runtimeQuery.data,
      hasPlayersData: !!playersQuery.data,
      
      // 状态判断
      isRunning: statusQuery.data && ['RUNNING', 'STARTING', 'HEALTHY'].includes(statusQuery.data),
      isHealthy: statusQuery.data === 'HEALTHY',
      
      // 组合数据对象 (用于传递给组件)
      serverData: configQuery.data ? {
        ...configQuery.data,
        status: statusQuery.data,
        runtime: runtimeQuery.data,
        onlinePlayers: playersQuery.data || [],
        // 添加计算属性
        memoryUsagePercent: runtimeQuery.data && configQuery.data
          ? (runtimeQuery.data.memoryUsageBytes / configQuery.data.maxMemoryBytes) * 100
          : 0,
        
        // 格式化的显示值
        displayMemoryUsage: runtimeQuery.data && configQuery.data
          ? `${(runtimeQuery.data.memoryUsageBytes / (1024 ** 3)).toFixed(1)}GB / ${(configQuery.data.maxMemoryBytes / (1024 ** 3)).toFixed(1)}GB`
          : '未知',
          
        displayCpuUsage: runtimeQuery.data
          ? `${runtimeQuery.data.cpuPercentage.toFixed(1)}%`
          : '未知'
      } : undefined
    }
  }
  
  return {
    useServerDetailData
  }
}
