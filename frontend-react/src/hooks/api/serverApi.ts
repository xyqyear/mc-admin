import type { ServerInfo, ServerStatus } from '@/types/ServerInfo'
import type { ServerRuntime, SystemInfo } from '@/types/ServerRuntime'
import { api } from '@/utils/api'

// Backend API response types (matching backend Pydantic models)
interface ServerListItem {
  id: string
  name: string
  serverType: string
  gameVersion: string
  gamePort: number
  status: ServerStatus
  onlinePlayers: string[]
  maxMemoryBytes: number
  rconPort: number
  cpuPercentage?: number
  memoryUsageBytes?: number
}

interface ServerStatusResponse {
  status: ServerStatus
}

interface ServerRuntimeResponse {
  onlinePlayers: string[]
  cpuPercentage: number
  memoryUsageBytes: number
}

interface ServerOperationRequest {
  action: string
}

export const serverApi = {
  // 获取所有服务器信息 (新的综合API，替代之前分离的配置和状态API)
  getServers: async (): Promise<ServerListItem[]> => {
    const res = await api.get<ServerListItem[]>('/servers/')
    return res.data
  },
  
  // 获取单个服务器详细配置信息
  getServerInfo: async (id: string): Promise<ServerInfo> => {
    const res = await api.get<{
      id: string
      name: string
      serverType: string
      gameVersion: string
      gamePort: number
      maxMemoryBytes: number
      rconPort: number
    }>(`/servers/${id}/`)
    
    // Transform backend response to match frontend ServerInfo type
    return {
      id: res.data.id,
      name: res.data.name,
      path: `/servers/${id}`, // Default path
      javaVersion: 17, // Default Java version
      maxMemoryBytes: res.data.maxMemoryBytes,
      serverType: res.data.serverType.toUpperCase() as any,
      gameVersion: res.data.gameVersion,
      gamePort: res.data.gamePort,
      rconPort: res.data.rconPort, // Use real RCON port from backend
    }
  },
  
  // 获取单个服务器状态
  getServerStatus: async (id: string): Promise<ServerStatus> => {
    const res = await api.get<ServerStatusResponse>(`/servers/${id}/status`)
    return res.data.status
  },
  
  // 获取单个服务器运行时信息 (仅在服务器运行时可用)
  getServerRuntime: async (id: string): Promise<ServerRuntime> => {
    const res = await api.get<ServerRuntimeResponse>(`/servers/${id}/runtime`)
    
    // Transform to match frontend ServerRuntime type
    return {
      serverId: id,
      status: 'RUNNING' as ServerStatus, // Assume running if we can get runtime data
      cpuPercentage: res.data.cpuPercentage,
      memoryUsageBytes: res.data.memoryUsageBytes,
      diskReadBytes: 0, // TODO: Add when backend supports disk I/O stats
      diskWriteBytes: 0,
      networkReceiveBytes: 0, // TODO: Add when backend supports network stats  
      networkSendBytes: 0,
      diskUsageBytes: 0, // TODO: Add disk usage calculation
      onlinePlayers: res.data.onlinePlayers,
      containerId: undefined, // Optional fields
      pid: undefined,
    }
  },
  
  // 服务器操作 (统一的操作API)
  serverOperation: async (id: string, action: string): Promise<void> => {
    await api.post(`/servers/${id}/operations`, { action } as ServerOperationRequest)
  },
  
  // 便捷的操作方法 (保持向后兼容)
  startServer: async (id: string): Promise<void> => {
    await serverApi.serverOperation(id, 'start')
  },
  
  stopServer: async (id: string): Promise<void> => {
    await serverApi.serverOperation(id, 'stop')
  },
  
  restartServer: async (id: string): Promise<void> => {
    await serverApi.serverOperation(id, 'restart')
  },
  
  upServer: async (id: string): Promise<void> => {
    await serverApi.serverOperation(id, 'up')
  },
  
  downServer: async (id: string): Promise<void> => {
    await serverApi.serverOperation(id, 'down')
  },
  
  // 获取在线玩家 (从运行时信息中提取)
  getOnlinePlayers: async (id: string): Promise<string[]> => {
    try {
      const runtime = await serverApi.getServerRuntime(id)
      return runtime.onlinePlayers
    } catch (error) {
      // Server might not be running
      return []
    }
  },
  
  // Compose文件API (保持现有接口，但需要后端支持)
  getComposeFile: async (_id: string): Promise<string> => {
    // TODO: Implement when backend adds compose file endpoint
    // const res = await api.get<{content: string}>(`/servers/${id}/compose`)
    // return res.data.content
    throw new Error('Compose file API not yet implemented in backend')
  },
  
  // RCON命令API (保持现有接口，但需要后端支持) 
  sendRconCommand: async (_id: string, _command: string): Promise<string> => {
    // TODO: Implement when backend adds RCON endpoint
    // const res = await api.post<{result: string}>(`/servers/${id}/rcon`, { command })
    // return res.data.result
    throw new Error('RCON API not yet implemented in backend')
  },
  
  // 批量获取服务器状态 (优化的API，减少网络请求)
  getAllServerStatuses: async (_serverIds: string[]): Promise<Record<string, ServerStatus>> => {
    // Use the comprehensive servers endpoint which includes status
    const servers = await serverApi.getServers()
    
    const statusMap: Record<string, ServerStatus> = {}
    servers.forEach(server => {
      statusMap[server.id] = server.status
    })
    
    return statusMap
  },
  
  // 批量获取服务器运行时信息 
  getAllServerRuntimes: async (serverIds: string[]): Promise<Record<string, ServerRuntime | null>> => {
    const runtimePromises = serverIds.map(async (id) => {
      try {
        const runtime = await serverApi.getServerRuntime(id)
        return { id, runtime }
      } catch (error) {
        return { id, runtime: null }
      }
    })
    
    const results = await Promise.allSettled(runtimePromises)
    
    const runtimeMap: Record<string, ServerRuntime | null> = {}
    results.forEach((result) => {
      if (result.status === 'fulfilled' && result.value) {
        runtimeMap[result.value.id] = result.value.runtime
      }
    })
    
    return runtimeMap
  }
}

export const systemApi = {
  getSystemInfo: async (): Promise<SystemInfo> => {
    const res = await api.get<SystemInfo>('/system/info')
    return res.data
  }
}

// Export types for use in other modules
export type { ServerListItem, ServerRuntimeResponse, ServerStatusResponse }
