import type { ServerStatus } from "@/types/ServerInfo";

// Mirrors MCServerRunningInfo from minecraft-docker-manager-lib.
export interface ServerRuntime {
  serverId: string;
  status: ServerStatus;
  cpuPercentage: number;
  memoryUsageBytes: number;
  diskReadBytes: number;
  diskWriteBytes: number;
  networkReceiveBytes: number;
  networkSendBytes: number;
  diskUsageBytes: number;
  diskTotalBytes: number;
  diskAvailableBytes: number;
  onlinePlayers: string[];
  containerId?: string;
  pid?: number;
}

export interface SystemInfo {
  cpuPercentage: number;
  cpuLoad1Min: number;
  cpuLoad5Min: number;
  cpuLoad15Min: number;
  ramUsedGB: number;
  ramTotalGB: number;
}

export interface SystemDiskUsage {
  diskUsedGB: number;
  diskTotalGB: number;
  diskAvailableGB: number;
}

export interface BackupRepositoryUsage {
  backupUsedGB: number;
  backupTotalGB: number;
  backupAvailableGB: number;
}

import type { ServerInfo } from "@/types/ServerInfo";

export interface ServerFullInfo extends ServerInfo {
  runtime?: ServerRuntime;
}
