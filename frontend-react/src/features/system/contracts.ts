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
