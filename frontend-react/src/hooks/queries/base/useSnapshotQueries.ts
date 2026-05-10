import { useQuery, type UseQueryOptions } from "@tanstack/react-query";
import {
  snapshotApi,
  type Snapshot,
  type BackupRepositoryUsage,
  type ListLocksResponse,
} from "@/hooks/api/snapshotApi";
import { queryKeys } from "@/utils/api";

export const useSnapshotQueries = () => {
  const useGlobalSnapshots = (options?: UseQueryOptions<Snapshot[]>) => {
    return useQuery({
      queryKey: queryKeys.snapshots.global(),
      queryFn: () => snapshotApi.getAllSnapshots(),
      staleTime: 2 * 60 * 1000,
      refetchInterval: false,
      ...options,
    });
  };

  const useSnapshotsForPath = (
    serverId: string | null,
    path: string | null,
    enabled: boolean = true,
    options?: UseQueryOptions<Snapshot[]>
  ) => {
    return useQuery({
      queryKey: queryKeys.snapshots.forPath(serverId || "", path || ""),
      queryFn: () => snapshotApi.getAllSnapshots({
        server_id: serverId!,
        path: path!
      }),
      enabled: enabled && !!serverId && !!path,
      staleTime: 1 * 60 * 1000,
      refetchInterval: false,
      ...options,
    });
  };

  const useBackupRepositoryUsage = (options?: UseQueryOptions<BackupRepositoryUsage>) => {
    return useQuery({
      queryKey: queryKeys.snapshots.repositoryUsage(),
      queryFn: snapshotApi.getBackupRepositoryUsage,
      refetchInterval: 30000,
      staleTime: 15000,
      retry: (failureCount, error: any) => {
        // Restic-not-configured surfaces as a 500 with 'restic' in the message; don't hammer it.
        if (error?.response?.status === 500 && error?.message?.includes('restic')) return false;
        return failureCount < 2;
      },
      ...options,
    });
  };

  // Locks are manually fetched (admin action), not polled.
  const useSnapshotLocks = (
    enabled: boolean = false,
    options?: UseQueryOptions<ListLocksResponse>
  ) => {
    return useQuery({
      queryKey: queryKeys.snapshots.locks(),
      queryFn: snapshotApi.listLocks,
      enabled,
      staleTime: 0,
      refetchInterval: false,
      ...options,
    });
  };

  return {
    useGlobalSnapshots,
    useSnapshotsForPath,
    useBackupRepositoryUsage,
    useSnapshotLocks,
  };
};
