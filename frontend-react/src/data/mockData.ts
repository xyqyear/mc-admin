import type { ServerInfo, ServerType } from '@/types/ServerInfo'
import type { ServerRuntime, SystemInfo } from '@/types/ServerRuntime'

// Mock 服务器配置信息 - 基于实际的开发服务器数据
export const mockServerInfos: ServerInfo[] = [
  {
    id: 'server1',
    name: 'server1',
    path: '/mnt/c/Users/xyqye/Desktop/Data/Sync/code/minecraft/mc-admin/backend/dev-servers/server1',
    javaVersion: 21,
    maxMemoryBytes: 1024 * 1024 * 1024, // 1GB
    serverType: 'VANILLA' as ServerType,
    gameVersion: '1.20.1',
    gamePort: 25517,
    rconPort: 25617,
  },
  {
    id: 'server2',
    name: 'server2', 
    path: '/mnt/c/Users/xyqye/Desktop/Data/Sync/code/minecraft/mc-admin/backend/dev-servers/server2',
    javaVersion: 21,
    maxMemoryBytes: 1024 * 1024 * 1024, // 1GB
    serverType: 'VANILLA' as ServerType,
    gameVersion: '1.20.1',
    gamePort: 25521,
    rconPort: 25621,
  },
  {
    id: 'vanilla',
    name: 'Vanilla Survival Server',
    path: '/servers/vanilla-survival',
    javaVersion: 21,
    maxMemoryBytes: 4096 * 1024 * 1024, // 4GB
    serverType: 'VANILLA' as ServerType,
    gameVersion: '1.21.1',
    gamePort: 25565,
    rconPort: 25575,
  },
  {
    id: 'creative-test',
    name: 'creative-test',
    path: '/servers/creative-test',
    javaVersion: 21,
    maxMemoryBytes: 2048 * 1024 * 1024, // 2GB
    serverType: 'PAPER' as ServerType,
    gameVersion: '1.21.1',
    gamePort: 25566,
    rconPort: 25576,
  },
  {
    id: 'modded-forge',
    name: 'modded-forge',
    path: '/servers/modded-forge',
    javaVersion: 17,
    maxMemoryBytes: 8192 * 1024 * 1024, // 8GB
    serverType: 'FORGE' as ServerType,
    gameVersion: '1.20.1',
    gamePort: 25567,
    rconPort: 25577,
  }
]

// Mock 服务器运行时信息
export const mockServerRuntimes: Record<string, ServerRuntime> = {
  'server1': {
    serverId: 'server1',
    status: 'HEALTHY',
    cpuPercentage: 15.5,
    memoryUsageBytes: 1341 * 1024 * 1024, // 1341MB
    diskReadBytes: 0,
    diskWriteBytes: 0.3 * 1024 * 1024, // 0.3MB
    networkReceiveBytes: 0,
    networkSendBytes: 0,
    diskUsageBytes: 172 * 1024 * 1024, // 172MB
    diskTotalBytes: 10 * 1024 * 1024 * 1024, // 10GB
    diskAvailableBytes: (10 * 1024 * 1024 * 1024) - (172 * 1024 * 1024), // 10GB - 172MB
    onlinePlayers: [],
    containerId: 'd34ad1b43f7e12345678',
    pid: 1066064,
  },
  'server2': {
    serverId: 'server2',
    status: 'HEALTHY',
    cpuPercentage: 12.3,
    memoryUsageBytes: 1200 * 1024 * 1024, // 1200MB
    diskReadBytes: 45.2 * 1024 * 1024,
    diskWriteBytes: 23.1 * 1024 * 1024,
    networkReceiveBytes: 12.4 * 1024 * 1024,
    networkSendBytes: 18.9 * 1024 * 1024,
    diskUsageBytes: 180 * 1024 * 1024,
    diskTotalBytes: 8 * 1024 * 1024 * 1024, // 8GB
    diskAvailableBytes: (8 * 1024 * 1024 * 1024) - (180 * 1024 * 1024), // 8GB - 180MB
    onlinePlayers: ['Steve', 'Alex'],
    containerId: 'a1b2c3d4e5f6789',
    pid: 1066123,
  },
  'creative-test': {
    serverId: 'creative-test',
    status: 'STARTING',
    cpuPercentage: 8.2,
    memoryUsageBytes: 800 * 1024 * 1024,
    diskReadBytes: 20 * 1024 * 1024,
    diskWriteBytes: 15 * 1024 * 1024,
    networkReceiveBytes: 5 * 1024 * 1024,
    networkSendBytes: 8 * 1024 * 1024,
    diskUsageBytes: 150 * 1024 * 1024,
    diskTotalBytes: 12 * 1024 * 1024 * 1024, // 12GB
    diskAvailableBytes: (12 * 1024 * 1024 * 1024) - (150 * 1024 * 1024), // 12GB - 150MB
    onlinePlayers: [],
    containerId: 'abc123def456',
    pid: 1066456,
  },
  'vanilla': {
    serverId: 'vanilla',
    status: 'HEALTHY',
    cpuPercentage: 18.7,
    memoryUsageBytes: 1500 * 1024 * 1024, // 1500MB
    diskReadBytes: 65 * 1024 * 1024,
    diskWriteBytes: 42 * 1024 * 1024,
    networkReceiveBytes: 25 * 1024 * 1024,
    networkSendBytes: 35 * 1024 * 1024,
    diskUsageBytes: 200 * 1024 * 1024,
    diskTotalBytes: 15 * 1024 * 1024 * 1024, // 15GB
    diskAvailableBytes: (15 * 1024 * 1024 * 1024) - (200 * 1024 * 1024), // 15GB - 200MB
    onlinePlayers: ['Player1', 'Player2', 'Player3'],
    containerId: 'vanilla123abc456',
    pid: 1066789,
  }
}

// Mock 服务器状态 (独立状态，可以与runtime不同)
export const mockServerStatuses: Record<string, import('@/types/ServerInfo').ServerStatus> = {
  'server1': 'HEALTHY',
  'server2': 'HEALTHY', 
  'creative-test': 'STARTING',
  'modded-forge': 'CREATED',
  'vanilla': 'HEALTHY',
}

// Mock 系统信息
export const mockSystemInfo: SystemInfo = {
  cpuPercentage: 25.6,
  cpuLoad1Min: 1.2,
  cpuLoad5Min: 1.5,
  cpuLoad15Min: 1.8,
  ramUsedGB: 8.4,
  ramTotalGB: 16.0,
  diskUsedGB: 120.5,
  diskTotalGB: 500.0,
  backupUsedGB: 25.3,
  backupTotalGB: 100.0,
}

// Mock 在线玩家数据
export const mockOnlinePlayers: Record<string, string[]> = {
  'server1': [],
  'server2': ['Steve', 'Alex'],
  'creative-test': [],
  'modded-forge': [],
  'vanilla': ['Player1', 'Player2', 'Player3'],
}

// Mock Compose文件内容
export const mockComposeFiles: Record<string, string> = {
  'server1': `services:
  mc:
    image: itzg/minecraft-server:java21-graalvm
    container_name: mc-server1
    environment:
      EULA: true
      TZ: Asia/Shanghai
      VERSION: 1.20.1
      INIT_MEMORY: 0G
      MAX_MEMORY: 1G
      ONLINE_MODE: true
      TYPE: VANILLA
    ports:
      - "25517:25565"
      - "25617:25575"
    volumes:
      - ./data:/data
    stdin_open: true
    tty: true
    restart: unless-stopped`,
  'server2': `services:
  mc:
    image: itzg/minecraft-server:java21-graalvm
    container_name: mc-server2
    environment:
      EULA: true
      TZ: Asia/Shanghai
      VERSION: 1.20.1
      INIT_MEMORY: 0G
      MAX_MEMORY: 1G
      ONLINE_MODE: true
      TYPE: VANILLA
    ports:
      - "25521:25565"
      - "25621:25575"
    volumes:
      - ./data:/data
    stdin_open: true
    tty: true
    restart: unless-stopped`,
  'creative-test': `services:
  mc:
    image: itzg/minecraft-server:java21-graalvm
    container_name: mc-creative-test
    environment:
      EULA: true
      TZ: Asia/Shanghai
      VERSION: 1.20.1
      INIT_MEMORY: 0G
      MAX_MEMORY: 2G
      ONLINE_MODE: false
      TYPE: VANILLA
      MODE: creative
      FORCE_GAMEMODE: true
    ports:
      - "25525:25565"
      - "25625:25575"
    volumes:
      - ./data:/data
    stdin_open: true
    tty: true
    restart: unless-stopped`,
  'modded-forge': `services:
  mc:
    image: itzg/minecraft-server:java17
    container_name: mc-modded-forge
    environment:
      EULA: true
      TZ: Asia/Shanghai
      VERSION: 1.20.1
      TYPE: FORGE
      FORGE_VERSION: 47.2.0
      INIT_MEMORY: 0G
      MAX_MEMORY: 8G
      ONLINE_MODE: true
    ports:
      - "25567:25565"
      - "25577:25575"
    volumes:
      - ./data:/data
      - ./mods:/data/mods
    stdin_open: true
    tty: true
    restart: unless-stopped`,
  'vanilla': `services:
  mc:
    image: itzg/minecraft-server:java21-graalvm
    container_name: mc-vanilla
    environment:
      EULA: true
      TZ: Asia/Shanghai
      VERSION: 1.21.1
      INIT_MEMORY: 0G
      MAX_MEMORY: 2G
      ONLINE_MODE: true
      TYPE: VANILLA
      DIFFICULTY: normal
      PVP: true
      SPAWN_PROTECTION: 16
    ports:
      - "25565:25565"
      - "25575:25575"
    volumes:
      - ./data:/data
    stdin_open: true
    tty: true
    restart: unless-stopped`
}
