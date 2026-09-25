import type { BackupRepositoryUsage } from "@/features/backups/contracts";
import { api } from "@/shared/http/api";
import type { Snapshot, CreateSnapshotResponse, ListSnapshotsResponse, DeleteSnapshotResponse, ListLocksResponse, UnlockResponse, RestorePreviewRequest, RestorePreviewResponse } from '@/features/backups/contracts';


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

  createSnapshot: async (params?: {
    server_id?: string;
    paths?: string[];
  }): Promise<CreateSnapshotResponse> => {
    const res = await api.post<CreateSnapshotResponse>("/snapshots", params || {});
    return res.data;
  },

  previewRestore: async (data: RestorePreviewRequest): Promise<RestorePreviewResponse> => {
    const res = await api.post<RestorePreviewResponse>("/snapshots/restore/preview", data);
    return res.data;
  },

  createGlobalSnapshot: async (): Promise<CreateSnapshotResponse> => {
    return snapshotApi.createSnapshot();
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