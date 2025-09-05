import type { ServerInfo, ServerStatus } from "@/types/ServerInfo";
import type { SystemInfo } from "@/types/ServerRuntime";
import { api } from "@/utils/api";

// Backend API response types (matching backend Pydantic models)
interface ServerListItem {
  id: string;
  name: string;
  serverType: string;
  gameVersion: string;
  gamePort: number;
  maxMemoryBytes: number;
  rconPort: number;
}

interface ServerStatusResponse {
  status: ServerStatus;
}

interface ServerCpuPercentResponse {
  cpuPercentage: number;
}

interface ServerMemoryResponse {
  memoryUsageBytes: number;
}

interface ServerPlayersResponse {
  onlinePlayers: string[];
}

interface ServerIOStatsResponse {
  diskReadBytes: number;
  diskWriteBytes: number;
  networkReceiveBytes: number;
  networkSendBytes: number;
}

interface ServerDiskUsageResponse {
  diskUsageBytes: number;
  diskTotalBytes: number;
  diskAvailableBytes: number;
}

interface ServerOperationRequest {
  action: string;
}

interface ComposeConfigResponse {
  yaml_content: string;
}

interface ComposeConfigRequest {
  yaml_content: string;
}

export const serverApi = {
  // 获取所有服务器基础信息 (仅包含配置信息，不包含状态或运行时数据)
  getServers: async (): Promise<ServerListItem[]> => {
    const res = await api.get<ServerListItem[]>("/servers/");
    return res.data;
  },

  // 获取单个服务器详细配置信息
  getServerInfo: async (id: string): Promise<ServerInfo> => {
    const res = await api.get<{
      id: string;
      name: string;
      serverType: string;
      gameVersion: string;
      gamePort: number;
      maxMemoryBytes: number;
      rconPort: number;
    }>(`/servers/${id}/`);

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
    };
  },

  // 获取单个服务器状态
  getServerStatus: async (id: string): Promise<ServerStatus> => {
    const res = await api.get<ServerStatusResponse>(`/servers/${id}/status`);
    return res.data.status;
  },

  // 获取单个服务器CPU百分比 (在RUNNING/STARTING/HEALTHY状态下可用)
  getServerCpuPercent: async (
    id: string
  ): Promise<{ cpuPercentage: number }> => {
    const res = await api.get<ServerCpuPercentResponse>(
      `/servers/${id}/cpu_percent`
    );
    return {
      cpuPercentage: res.data.cpuPercentage,
    };
  },

  // 获取单个服务器内存使用量 (在RUNNING/STARTING/HEALTHY状态下可用)
  getServerMemory: async (
    id: string
  ): Promise<{ memoryUsageBytes: number }> => {
    const res = await api.get<ServerMemoryResponse>(`/servers/${id}/memory`);
    return {
      memoryUsageBytes: res.data.memoryUsageBytes,
    };
  },

  // 获取单个服务器玩家列表 (仅在HEALTHY状态下可用)
  getServerPlayers: async (id: string): Promise<string[]> => {
    const res = await api.get<ServerPlayersResponse>(`/servers/${id}/players`);
    return res.data.onlinePlayers;
  },

  // 获取单个服务器I/O统计信息 (在RUNNING/STARTING/HEALTHY状态下可用)
  getServerIOStats: async (id: string): Promise<ServerIOStatsResponse> => {
    const res = await api.get<ServerIOStatsResponse>(`/servers/${id}/iostats`);
    return res.data;
  },

  // 获取单个服务器磁盘使用信息 (始终可用，不依赖服务器状态)
  getServerDiskUsage: async (id: string): Promise<ServerDiskUsageResponse> => {
    const res = await api.get<ServerDiskUsageResponse>(
      `/servers/${id}/disk-usage`
    );
    return res.data;
  },

  // 服务器操作 (统一的操作API)
  serverOperation: async (id: string, action: string): Promise<void> => {
    await api.post(`/servers/${id}/operations`, {
      action,
    } as ServerOperationRequest);
  },

  // 便捷的操作方法 (保持向后兼容)
  startServer: async (id: string): Promise<void> => {
    await serverApi.serverOperation(id, "start");
  },

  stopServer: async (id: string): Promise<void> => {
    await serverApi.serverOperation(id, "stop");
  },

  restartServer: async (id: string): Promise<void> => {
    await serverApi.serverOperation(id, "restart");
  },

  upServer: async (id: string): Promise<void> => {
    await serverApi.serverOperation(id, "up");
  },

  downServer: async (id: string): Promise<void> => {
    await serverApi.serverOperation(id, "down");
  },

  removeServer: async (id: string): Promise<void> => {
    await serverApi.serverOperation(id, "remove");
  },

  // Compose文件API
  getComposeFile: async (id: string): Promise<string> => {
    const res = await api.get<ComposeConfigResponse>(`/servers/${id}/compose`);
    return res.data.yaml_content;
  },

  // 更新Compose文件
  updateComposeFile: async (id: string, yamlContent: string): Promise<void> => {
    await api.post(`/servers/${id}/compose`, {
      yaml_content: yamlContent,
    } as ComposeConfigRequest);
  },

  // RCON命令API
  sendRconCommand: async (id: string, command: string): Promise<string> => {
    const res = await api.post<{ result: string }>(`/servers/${id}/rcon`, {
      command,
    });
    return res.data.result;
  },

  // 批量获取服务器状态
  getAllServerStatuses: async (
    serverIds: string[]
  ): Promise<Record<string, ServerStatus>> => {
    // Since servers endpoint no longer includes status, fetch each server status individually
    const statusPromises = serverIds.map(async (id) => {
      try {
        const status = await serverApi.getServerStatus(id);
        return { id, status };
      } catch (error) {
        // If a server status fails, return null status to avoid breaking the whole request
        return { id, status: null };
      }
    });

    const statuses = await Promise.all(statusPromises);

    const statusMap: Record<string, ServerStatus> = {};
    statuses.forEach(({ id, status }) => {
      if (status !== null) {
        statusMap[id] = status;
      }
    });

    return statusMap;
  },
};

export const systemApi = {
  getSystemInfo: async (): Promise<SystemInfo> => {
    const res = await api.get<SystemInfo>("/system/info");
    return res.data;
  },

  getSystemCpuPercent: async (): Promise<{ cpuPercentage: number }> => {
    const res = await api.get<{ cpuPercentage: number }>("/system/cpu_percent");
    return res.data;
  },
};

// Snapshot management types
interface SnapshotSummary {
  backup_start: string;
  backup_end: string;
  files_new: number;
  files_changed: number;
  files_unmodified: number;
  dirs_new: number;
  dirs_changed: number;
  dirs_unmodified: number;
  data_blobs: number;
  tree_blobs: number;
  data_added: number;
  data_added_packed: number;
  total_files_processed: number;
  total_bytes_processed: number;
}

interface Snapshot {
  time: string;
  tree: string;
  paths: string[];
  hostname: string;
  username: string;
  id: string;
  short_id: string;
  program_version?: string;
  summary?: SnapshotSummary;
}

interface CreateSnapshotResponse {
  message: string;
  snapshot: Snapshot;
}

interface ListSnapshotsResponse {
  snapshots: Snapshot[];
}

export const snapshotApi = {
  // 列出所有快照 (不传入server_id和path)
  getAllSnapshots: async (): Promise<Snapshot[]> => {
    const res = await api.get<ListSnapshotsResponse>("/snapshots");
    return res.data.snapshots;
  },

  // 创建全局快照 (不传入server_id和path)
  createGlobalSnapshot: async (): Promise<CreateSnapshotResponse> => {
    const res = await api.post<CreateSnapshotResponse>("/snapshots", {});
    return res.data;
  },
};

// Export types for use in other modules
export type {
  ServerDiskUsageResponse, ServerIOStatsResponse, ServerListItem,
  ServerStatusResponse, Snapshot, CreateSnapshotResponse, ListSnapshotsResponse
};

