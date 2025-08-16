export interface ServerInfo {
  id: string
  onlinePlayers: string[]
  state: 'running' | 'paused' | 'stopped' | 'down'
  diskUsedGB: number
  port: number
}

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
