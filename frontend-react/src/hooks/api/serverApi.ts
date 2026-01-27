import type { ServerInfo, ServerStatus } from "@/types/ServerInfo";
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
  javaVersion: number;
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

interface CreateServerRequest {
  yaml_content: string;
}

interface PopulateServerRequest {
  archive_filename: string;
}

interface PopulateServerResponse {
  success: boolean;
  message: string;
}

interface RestartScheduleResponse {
  cronjob_id: string;
  server_id: string;
  name: string;
  cron: string;
  status: string;
  next_run_time: string | null;
  scheduled_time: string;
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
      javaVersion: number;
    }>(`/servers/${id}`);

    // Transform backend response to match frontend ServerInfo type
    return {
      id: res.data.id,
      name: res.data.name,
      path: `/servers/${id}`, // Default path
      javaVersion: res.data.javaVersion, // Default Java version
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
    id: string,
  ): Promise<{ cpuPercentage: number }> => {
    const res = await api.get<ServerCpuPercentResponse>(
      `/servers/${id}/cpu_percent`,
    );
    return {
      cpuPercentage: res.data.cpuPercentage,
    };
  },

  // 获取单个服务器内存使用量 (在RUNNING/STARTING/HEALTHY状态下可用)
  getServerMemory: async (
    id: string,
  ): Promise<{ memoryUsageBytes: number }> => {
    const res = await api.get<ServerMemoryResponse>(`/servers/${id}/memory`);
    return {
      memoryUsageBytes: res.data.memoryUsageBytes,
    };
  },

  // 获取单个服务器玩家列表 (仅在HEALTHY状态下可用)
  // DEPRECATED: Use playerApi.getServerOnlinePlayers instead for full player info with avatars
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
      `/servers/${id}/disk-usage`,
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

  // 创建新服务器
  createServer: async (
    serverId: string,
    request: CreateServerRequest,
  ): Promise<void> => {
    await api.post(`/servers/${serverId}`, request);
  },

  // 填充服务器数据
  populateServer: async (
    serverId: string,
    archiveFilename: string,
  ): Promise<PopulateServerResponse> => {
    const res = await api.post<PopulateServerResponse>(
      `/servers/${serverId}/populate`,
      {
        archive_filename: archiveFilename,
      } as PopulateServerRequest,
    );
    return res.data;
  },

  // 重启计划管理API
  createOrUpdateRestartSchedule: async (
    serverId: string,
    customCron?: string,
  ): Promise<RestartScheduleResponse> => {
    const res = await api.post<RestartScheduleResponse>(
      `/servers/${serverId}/restart-schedule`,
      {
        custom_cron: customCron,
      },
    );
    return res.data;
  },

  getRestartSchedule: async (
    serverId: string,
  ): Promise<RestartScheduleResponse | null> => {
    try {
      const res = await api.get<RestartScheduleResponse>(
        `/servers/${serverId}/restart-schedule`,
      );
      return res.data;
    } catch (error: any) {
      if (error.response?.status === 404) {
        return null;
      }
      throw error;
    }
  },

  deleteRestartSchedule: async (serverId: string): Promise<void> => {
    await api.delete(`/servers/${serverId}/restart-schedule`);
  },

  pauseRestartSchedule: async (serverId: string): Promise<void> => {
    await api.post(`/servers/${serverId}/restart-schedule/pause`);
  },

  resumeRestartSchedule: async (serverId: string): Promise<void> => {
    await api.post(`/servers/${serverId}/restart-schedule/resume`);
  },

  // 批量获取服务器状态
  getAllServerStatuses: async (
    serverIds: string[],
  ): Promise<Record<string, ServerStatus>> => {
    // Since servers endpoint no longer includes status, fetch each server status individually
    const statusPromises = serverIds.map(async (id) => {
      try {
        const status = await serverApi.getServerStatus(id);
        return { id, status };
      } catch {
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

// Export types for use in other modules
export type {
  CreateServerRequest,
  PopulateServerRequest,
  PopulateServerResponse,
  RestartScheduleResponse,
  ServerDiskUsageResponse,
  ServerIOStatsResponse,
  ServerListItem,
  ServerStatusResponse
};

