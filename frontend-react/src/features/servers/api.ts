import type { TaskAccepted } from '@/features/tasks/contracts';
import { getErrorStatus } from '@/shared/http/api';
import type { SyncRequest } from "@/features/servers/lifecycleContracts";
import type { ServerInfo } from "@/features/servers/contracts";
import { api } from "@/shared/http/api";
import type { ServerListItem, ServerOperationRequest, CreateServerRequest, PopulateServerRequest, PopulateServerResponse, RestartScheduleResponse } from '@/features/servers/contracts';


export const serverApi = {
  getServers: async (): Promise<ServerListItem[]> => {
    const res = await api.get<ServerListItem[]>("/servers/");
    return res.data;
  },

  getServerInfo: async (id: string): Promise<ServerInfo> => {
    const res = await api.get<{
      id: string;
      name: string;
      server_generation?: number | null;
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
      serverGeneration: res.data.server_generation,
      path: `/servers/${id}`,
      javaVersion: res.data.javaVersion,
      maxMemoryBytes: res.data.maxMemoryBytes,
      serverType: res.data.serverType.toUpperCase() as any,
      gameVersion: res.data.gameVersion,
      gamePort: res.data.gamePort,
      rconPort: res.data.rconPort,
    };
  },

  serverOperation: async (id: string, action: string): Promise<TaskAccepted> => {
    const res = await api.post<TaskAccepted>(`/servers/${id}/operations`, { action } as ServerOperationRequest);
    return res.data;
  },

  createServer: async (
    serverId: string,
    request: CreateServerRequest,
  ): Promise<TaskAccepted> => {
    const res = await api.post<TaskAccepted>(
      `/servers/${serverId}`,
      request,
    );
    return res.data;
  },

  // 服务器文件系统 ↔ 数据库 同步 (OWNER-only)
  syncServers: async (request: SyncRequest = {}): Promise<TaskAccepted> => {
    const res = await api.post<TaskAccepted>(`/servers/sync`, request);
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
    } catch (error) {
      if (getErrorStatus(error) === 404) {
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

};
