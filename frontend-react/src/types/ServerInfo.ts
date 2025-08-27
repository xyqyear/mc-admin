// 服务器配置信息 - 基于 minecraft-docker-manager-lib 的 MCServerInfo
export interface ServerInfo {
  id: string                    // 服务器名称
  name: string                  // 显示名称
  path: string                  // 服务器路径
  javaVersion: number           // Java版本
  maxMemoryBytes: number        // 最大内存(字节)
  serverType: ServerType        // 服务器类型
  gameVersion: string           // 游戏版本
  gamePort: number              // 游戏端口
  rconPort: number              // RCON端口
}

// 服务器类型 - 基于 minecraft-docker-manager-lib 的 ServerType
export type ServerType = 'VANILLA' | 'PAPER' | 'FORGE' | 'NEOFORGE' | 'FABRIC' | 'SPIGOT' | 'BUKKIT' | 'CUSTOM'

// 服务器状态 - 基于 minecraft-docker-manager-lib 的 MCServerStatus
export type ServerStatus = 'REMOVED' | 'EXISTS' | 'CREATED' | 'RUNNING' | 'STARTING' | 'HEALTHY'
