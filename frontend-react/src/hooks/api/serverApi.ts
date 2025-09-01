import type { ServerInfo, ServerStatus } from '@/types/ServerInfo'
import type { SystemInfo } from '@/types/ServerRuntime'
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
  diskUsageBytes?: number
  diskTotalBytes?: number
  diskAvailableBytes?: number
}

interface ServerStatusResponse {
  status: ServerStatus
}

interface ServerResourcesResponse {
  cpuPercentage: number
  memoryUsageBytes: number
}

interface ServerPlayersResponse {
  onlinePlayers: string[]
}

interface ServerIOStatsResponse {
  diskReadBytes: number
  diskWriteBytes: number
  networkReceiveBytes: number
  networkSendBytes: number
  diskUsageBytes: number
  diskTotalBytes: number
  diskAvailableBytes: number
}

interface ServerOperationRequest {
  action: string
}

interface ComposeConfigResponse {
  yaml_content: string
}

interface ComposeConfigRequest {
  yaml_content: string
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
  

  // 获取单个服务器系统资源 (在RUNNING/STARTING/HEALTHY状态下可用)
  getServerResources: async (id: string): Promise<{ cpuPercentage: number; memoryUsageBytes: number }> => {
    const res = await api.get<ServerResourcesResponse>(`/servers/${id}/resources`)
    return {
      cpuPercentage: res.data.cpuPercentage,
      memoryUsageBytes: res.data.memoryUsageBytes,
    }
  },

  // 获取单个服务器玩家列表 (仅在HEALTHY状态下可用)
  getServerPlayers: async (id: string): Promise<string[]> => {
    const res = await api.get<ServerPlayersResponse>(`/servers/${id}/players`)
    return res.data.onlinePlayers
  },

  // 获取单个服务器I/O统计信息 (在RUNNING/STARTING/HEALTHY状态下可用)
  getServerIOStats: async (id: string): Promise<ServerIOStatsResponse> => {
    const res = await api.get<ServerIOStatsResponse>(`/servers/${id}/iostats`)
    return res.data
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

  removeServer: async (id: string): Promise<void> => {
    await serverApi.serverOperation(id, 'remove')
  },
  
  
  // Compose文件API
  getComposeFile: async (id: string): Promise<string> => {
    const res = await api.get<ComposeConfigResponse>(`/servers/${id}/compose`)
    return res.data.yaml_content
  },

  // 更新Compose文件
  updateComposeFile: async (id: string, yamlContent: string): Promise<void> => {
    await api.post(`/servers/${id}/compose`, { yaml_content: yamlContent } as ComposeConfigRequest)
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
  
}

export const systemApi = {
  getSystemInfo: async (): Promise<SystemInfo> => {
    const res = await api.get<SystemInfo>('/system/info')
    return res.data
  }
}

// Export types for use in other modules
export type { ServerListItem, ServerStatusResponse, ServerIOStatsResponse }
