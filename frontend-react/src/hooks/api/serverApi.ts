import type {
  CreateServerResult,
  RemoveServerResult,
  SyncRequest,
  SyncResult,
} from "@/types/lifecycle";
import type { ServerInfo, ServerStatus } from "@/types/ServerInfo";
import { api } from "@/utils/api";

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

interface ComposeUpdateResponse {
  task_id: string;
}

interface RestartScheduleRequestBody {
  custom_cron?: string | null;
}

interface CreateServerRequest {
  yaml_content?: string;
  template_id?: number;
  variable_values?: Record<string, unknown>;
  restart_schedule?: RestartScheduleRequestBody | null;
}

interface PopulateServerRequest {
  archive_filename: string;
}

interface PopulateServerResponse {
  task_id: string
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
  getServers: async (): Promise<ServerListItem[]> => {
    const res = await api.get<ServerListItem[]>("/servers/");
    return res.data;
  },

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

    return {
      id: res.data.id,
      name: res.data.name,
      path: `/servers/${id}`,
      javaVersion: res.data.javaVersion,
      maxMemoryBytes: res.data.maxMemoryBytes,
      serverType: res.data.serverType.toUpperCase() as any,
      gameVersion: res.data.gameVersion,
      gamePort: res.data.gamePort,
      rconPort: res.data.rconPort,
    };
  },

  getServerStatus: async (id: string): Promise<ServerStatus> => {
    const res = await api.get<ServerStatusResponse>(`/servers/${id}/status`);
    return res.data.status;
  },

  // Backend returns 4xx unless server is RUNNING/STARTING/HEALTHY.
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

  // Backend returns 4xx unless server is RUNNING/STARTING/HEALTHY.
  getServerMemory: async (
    id: string,
  ): Promise<{ memoryUsageBytes: number }> => {
    const res = await api.get<ServerMemoryResponse>(`/servers/${id}/memory`);
    return {
      memoryUsageBytes: res.data.memoryUsageBytes,
    };
  },

  // DEPRECATED: prefer playerApi.getServerOnlinePlayers (returns avatar/uuid).
  // Backend requires HEALTHY status.
  getServerPlayers: async (id: string): Promise<string[]> => {
    const res = await api.get<ServerPlayersResponse>(`/servers/${id}/players`);
    return res.data.onlinePlayers;
  },

  // Backend returns 4xx unless server is RUNNING/STARTING/HEALTHY.
  getServerIOStats: async (id: string): Promise<ServerIOStatsResponse> => {
    const res = await api.get<ServerIOStatsResponse>(`/servers/${id}/iostats`);
    return res.data;
  },

  getServerDiskUsage: async (id: string): Promise<ServerDiskUsageResponse> => {
    const res = await api.get<ServerDiskUsageResponse>(
      `/servers/${id}/disk-usage`,
    );
    return res.data;
  },

  serverOperation: async (id: string, action: string): Promise<void> => {
    await api.post(`/servers/${id}/operations`, {
      action,
    } as ServerOperationRequest);
  },

  removeServerFull: async (id: string): Promise<RemoveServerResult> => {
    const res = await api.post<RemoveServerResult>(
      `/servers/${id}/operations`,
      { action: "remove" } as ServerOperationRequest,
    );
    return res.data;
  },

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

  getComposeFile: async (id: string): Promise<string> => {
    const res = await api.get<ComposeConfigResponse>(`/servers/${id}/compose`);
    return res.data.yaml_content;
  },

  // Returns a task_id; rebuild progress is polled via the task API.
  updateComposeFile: async (id: string, yamlContent: string): Promise<ComposeUpdateResponse> => {
    const res = await api.post<ComposeUpdateResponse>(`/servers/${id}/compose`, {
      yaml_content: yamlContent,
    } as ComposeConfigRequest);
    return res.data;
  },

  createServer: async (
    serverId: string,
    request: CreateServerRequest,
  ): Promise<CreateServerResult> => {
    const res = await api.post<CreateServerResult>(
      `/servers/${serverId}`,
      request,
    );
    return res.data;
  },

  // 服务器文件系统 ↔ 数据库 同步 (OWNER-only)
  syncServers: async (request: SyncRequest = {}): Promise<SyncResult> => {
    const res = await api.post<SyncResult>(`/servers/sync`, request);
    return res.data;
  },

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

  // The list endpoint omits status, so fan out per server. A single failure
  // must not poison the rest, so map errors to null and filter later.
  getAllServerStatuses: async (
    serverIds: string[],
  ): Promise<Record<string, ServerStatus>> => {
    const statusPromises = serverIds.map(async (id) => {
      try {
        const status = await serverApi.getServerStatus(id);
        return { id, status };
      } catch {
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

export type {
  ComposeUpdateResponse,
  CreateServerRequest,
  PopulateServerRequest,
  PopulateServerResponse,
  RestartScheduleResponse,
  ServerDiskUsageResponse,
  ServerIOStatsResponse,
  ServerListItem,
  ServerStatusResponse
};

