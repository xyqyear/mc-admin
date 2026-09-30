import type { BackupRepositoryUsage } from "@/features/backups/contracts";
import { api } from "@/shared/http/api";
import type { Snapshot, SnapshotScope, SnapshotTaskAccepted, SnapshotRestoreRequest, RestorationHistory, ListSnapshotsResponse, ListLocksResponse, SnapshotPreviewRequest, SnapshotPreviewResult, SnapshotPreviewActions } from '@/features/backups/contracts';


export const snapshotApi = {
  eligible: async (scope: SnapshotScope) => (await api.post<ListSnapshotsResponse>('/snapshots/eligible', { scope })).data,
  getAllSnapshots: async (params?: {
    server_id?: string;
    path?: string;
  }): Promise<Snapshot[]> => {
    const queryParams = new URLSearchParams();
    if (params?.server_id) queryParams.set('server_id', params.server_id);
    if (params?.path) queryParams.set('path', params.path);

    const url = `/snapshots${queryParams.toString() ? `?${queryParams.toString()}` : ''}`;
    const res = await api.get<ListSnapshotsResponse>(url);
    return res.data.snapshots;
  },

  createSnapshot: async (scope: SnapshotScope): Promise<SnapshotTaskAccepted> => {
    const res = await api.post<SnapshotTaskAccepted>("/snapshots", { scope });
    return res.data;
  },

  preparePreview: async (request: SnapshotPreviewRequest) =>
    (await api.post<SnapshotTaskAccepted>('/snapshots/previews', request)).data,
  getPreview: async (id: string) => (await api.get<SnapshotPreviewResult>(`/snapshots/previews/${id}`)).data,
  previewActions: async (id: string, cursor = 0) =>
    (await api.get<SnapshotPreviewActions>(`/snapshots/previews/${id}/actions`, { params: { cursor, limit: 100 } })).data,
  heartbeatPreview: async (id: string) => { await api.post(`/snapshots/previews/${id}/heartbeat`) },
  closePreview: async (id: string) =>
    (await api.delete<SnapshotTaskAccepted>(`/snapshots/previews/${id}`)).data,

  restore: async (request: SnapshotRestoreRequest): Promise<SnapshotTaskAccepted> => {
    return (await api.post<SnapshotTaskAccepted>('/snapshots/restorations', request)).data;
  },

  rollback: async (id: string): Promise<SnapshotTaskAccepted> => {
    return (await api.post<SnapshotTaskAccepted>(`/snapshots/restorations/${id}/rollback`)).data;
  },

  history: async (serverId?: string, offset = 0): Promise<RestorationHistory> => {
    return (await api.get<RestorationHistory>('/snapshots/restorations', { params: { server_id: serverId, offset, limit: 50 } })).data;
  },

  getBackupRepositoryUsage: async (): Promise<BackupRepositoryUsage> => {
    const res = await api.get<BackupRepositoryUsage>("/snapshots/usage");
    return res.data;
  },

  deleteSnapshot: async (snapshotId: string): Promise<SnapshotTaskAccepted> => {
    const res = await api.delete<SnapshotTaskAccepted>(`/snapshots/${snapshotId}`);
    return res.data;
  },

  listLocks: async (): Promise<ListLocksResponse> => {
    const res = await api.get<ListLocksResponse>("/snapshots/locks");
    return res.data;
  },

  unlockRepository: async (): Promise<SnapshotTaskAccepted> => {
    const res = await api.post<SnapshotTaskAccepted>("/snapshots/unlock");
    return res.data;
  },
};
