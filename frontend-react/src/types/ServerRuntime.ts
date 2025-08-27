import type { ServerStatus } from './ServerInfo'

// 服务器运行时信息 - 基于 minecraft-docker-manager-lib 的 MCServerRunningInfo
export interface ServerRuntime {
  serverId: string
  status: ServerStatus
  cpuPercentage: number         // CPU使用率
  memoryUsageBytes: number      // 内存使用(字节)
  diskReadBytes: number         // 磁盘读取(字节)
  diskWriteBytes: number        // 磁盘写入(字节) 
  networkReceiveBytes: number   // 网络接收(字节)
  networkSendBytes: number      // 网络发送(字节)
  diskUsageBytes: number        // 磁盘使用量(字节)
  onlinePlayers: string[]       // 在线玩家列表
  containerId?: string          // 容器ID
  pid?: number                  // 进程PID
}

// 系统信息 - 保持现有结构
export interface SystemInfo {
  cpuPercentage: number
  cpuLoad1Min: number
  cpuLoad5Min: number
  cpuLoad15Min: number
  ramUsedGB: number
  ramTotalGB: number
  diskUsedGB: number
  diskTotalGB: number
  backupUsedGB: number
  backupTotalGB: number
}

// 组合视图类型 (仅用于前端展示)
import type { ServerInfo } from './ServerInfo'

export interface ServerFullInfo extends ServerInfo {
  runtime?: ServerRuntime      // 可选的运行时信息
}
