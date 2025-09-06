import type { ServerStatus } from "./ServerInfo";

// 服务器运行时信息 - 基于 minecraft-docker-manager-lib 的 MCServerRunningInfo
export interface ServerRuntime {
  serverId: string;
  status: ServerStatus;
  cpuPercentage: number; // CPU使用率
  memoryUsageBytes: number; // 内存使用(字节)
  diskReadBytes: number; // 磁盘读取(字节)
  diskWriteBytes: number; // 磁盘写入(字节)
  networkReceiveBytes: number; // 网络接收(字节)
  networkSendBytes: number; // 网络发送(字节)
  diskUsageBytes: number; // 磁盘使用量(字节)
  diskTotalBytes: number; // 磁盘总空间(字节)
  diskAvailableBytes: number; // 磁盘可用空间(字节)
  onlinePlayers: string[]; // 在线玩家列表
  containerId?: string; // 容器ID
  pid?: number; // 进程PID
}

// 系统信息 - 更新后的结构
export interface SystemInfo {
  cpuPercentage: number;
  cpuLoad1Min: number;
  cpuLoad5Min: number;
  cpuLoad15Min: number;
  ramUsedGB: number;
  ramTotalGB: number;
}

// 系统磁盘使用信息
export interface SystemDiskUsage {
  diskUsedGB: number;
  diskTotalGB: number;
  diskAvailableGB: number;
}

// 备份仓库使用信息
export interface BackupRepositoryUsage {
  backupUsedGB: number;
  backupTotalGB: number;
  backupAvailableGB: number;
}

// 组合视图类型 (仅用于前端展示)
import type { ServerInfo } from "./ServerInfo";

export interface ServerFullInfo extends ServerInfo {
  runtime?: ServerRuntime; // 可选的运行时信息
}
