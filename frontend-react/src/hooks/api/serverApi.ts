// import api from '@/utils/api' // 暂时注释，使用mock数据
import {
  mockComposeFiles,
  mockOnlinePlayers,
  mockServerInfos,
  mockServerRuntimes,
  mockServerStatuses,
  mockSystemInfo
} from '@/data/mockData'
import type { ServerInfo, ServerStatus } from '@/types/ServerInfo'
import type { ServerRuntime, SystemInfo } from '@/types/ServerRuntime'

// 模拟网络延迟
const delay = (ms: number) => new Promise(resolve => setTimeout(resolve, ms))

export const serverApi = {
  // 配置信息API (总是可获取)
  getServerInfos: async (): Promise<ServerInfo[]> => {
    await delay(100) // 模拟网络延迟
    // const res = await api.get<ServerInfo[]>('/servers/configs')
    // return res.data
    return mockServerInfos
  },
  
  getServerInfo: async (id: string): Promise<ServerInfo> => {
    await delay(50)
    // const res = await api.get<ServerInfo>(`/servers/${id}/config`)
    // return res.data
    const serverInfo = mockServerInfos.find(s => s.id === id)
    if (!serverInfo) {
      throw new Error(`Server ${id} not found`)
    }
    return serverInfo
  },
  
  // 运行时信息API (仅运行时可获取)
  getServerRuntime: async (id: string): Promise<ServerRuntime> => {
    await delay(80)
    // const res = await api.get<ServerRuntime>(`/servers/${id}/runtime`)
    // return res.data
    const runtime = mockServerRuntimes[id]
    if (!runtime) {
      throw new Error(`Runtime info not available for server ${id}`)
    }
    return runtime
  },
  
  // 服务器状态API (总是可获取)
  getServerStatus: async (id: string): Promise<ServerStatus> => {
    await delay(30)
    // const res = await api.get<{status: ServerStatus}>(`/servers/${id}/status`)
    // return res.data.status
    const status = mockServerStatuses[id]
    if (!status) {
      throw new Error(`Status not available for server ${id}`)
    }
    return status
  },
  
  // 玩家相关API (仅健康状态可获取)
  getOnlinePlayers: async (id: string): Promise<string[]> => {
    await delay(60)
    // const res = await api.get<string[]>(`/servers/${id}/players`)
    // return res.data
    return mockOnlinePlayers[id] || []
  },
  
  // Compose文件API
  getComposeFile: async (id: string): Promise<string> => {
    await delay(40)
    // const res = await api.get<{content: string}>(`/servers/${id}/compose`)
    // return res.data.content
    const composeFile = mockComposeFiles[id]
    if (!composeFile) {
      throw new Error(`Compose file not found for server ${id}`)
    }
    return composeFile
  },
  
  // 服务器操作API
  startServer: async (id: string): Promise<void> => {
    await delay(200)
    // await api.post(`/servers/${id}/start`)
    console.log(`Mock: Starting server ${id}`)
  },
  
  stopServer: async (id: string): Promise<void> => {
    await delay(200)
    // await api.post(`/servers/${id}/stop`)
    console.log(`Mock: Stopping server ${id}`)
  },
  
  restartServer: async (id: string): Promise<void> => {
    await delay(300)
    // await api.post(`/servers/${id}/restart`)
    console.log(`Mock: Restarting server ${id}`)
  },
  
  // RCON命令API (仅健康状态可用)
  sendRconCommand: async (id: string, command: string): Promise<string> => {
    await delay(100)
    // const res = await api.post<{result: string}>(`/servers/${id}/rcon`, { command })
    // return res.data.result
    return `Mock RCON response for "${command}" on server ${id}`
  }
}

export const systemApi = {
  getSystemInfo: async (): Promise<SystemInfo> => {
    await delay(120)
    // const res = await api.get<SystemInfo>('/system/info')
    // return res.data
    return mockSystemInfo
  }
}
