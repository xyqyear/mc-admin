import type { BackupRepositoryUsage } from "@/features/backups/contracts";
import { api } from "@/shared/http/api";
import type { Snapshot, SnapshotScope, SnapshotTaskAccepted, SnapshotRestoreRequest, RestorationHistory, ListSnapshotsResponse, DeleteSnapshotResponse, ListLocksResponse, UnlockResponse, RestorePreviewRequest, RestorePreviewResponse } from '@/features/backups/contracts';


export const snapshotApi = {
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

  previewRestore: async (data: RestorePreviewRequest): Promise<RestorePreviewResponse> => {
    const res = await api.post<RestorePreviewResponse>("/snapshots/restore/preview", data);
    return res.data;
  },

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
    const res = await api.get<BackupRepositoryUsage>("/snapshots/repository-usage");
    return res.data;
  },

  deleteSnapshot: async (snapshotId: string): Promise<DeleteSnapshotResponse> => {
    const res = await api.delete<DeleteSnapshotResponse>(`/snapshots/${snapshotId}`);
    return res.data;
  },

  listLocks: async (): Promise<ListLocksResponse> => {
    const res = await api.get<ListLocksResponse>("/snapshots/locks");
    return res.data;
  },

  unlockRepository: async (): Promise<UnlockResponse> => {
    const res = await api.post<UnlockResponse>("/snapshots/unlock");
    return res.data;
  },
};
