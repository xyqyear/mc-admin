import { queryOptions } from '@tanstack/react-query';
import { getErrorStatus, shouldRetryQuery } from '@/shared/http/api';
import { useQuery } from "@tanstack/react-query";
import { snapshotApi } from "@/features/backups/api";
import { queryKeys } from "@/shared/http/api";
export const useSnapshotQueries = () => {
  const useGlobalSnapshots = (options?: Partial<Omit<ReturnType<typeof globalSnapshotsQueryOptions>, 'queryKey' | 'queryFn'>>) => {
    return useQuery({ ...globalSnapshotsQueryOptions(), ...options });
  };
  const useSnapshotsForPath = (serverId: string | null, path: string | null, enabled: boolean = true, options?: Partial<Omit<ReturnType<typeof snapshotsForPathQueryOptions>, 'queryKey' | 'queryFn'>>) => {
    return useQuery({ ...snapshotsForPathQueryOptions(serverId, path, enabled), ...options });
  };
  const useBackupRepositoryUsage = (options?: Partial<Omit<ReturnType<typeof backupRepositoryUsageQueryOptions>, 'queryKey' | 'queryFn'>>) => {
    return useQuery({ ...backupRepositoryUsageQueryOptions(), ...options });
  };
  // Locks are manually fetched (admin action), not polled.
  const useSnapshotLocks = (enabled: boolean = false, options?: Partial<Omit<ReturnType<typeof snapshotLocksQueryOptions>, 'queryKey' | 'queryFn'>>) => {
    return useQuery({ ...snapshotLocksQueryOptions(enabled), ...options });
  };
  return {
    useGlobalSnapshots,
    useSnapshotsForPath,
    useBackupRepositoryUsage,
    useSnapshotLocks,
  };
};
export const globalSnapshotsQueryOptions = () => {
  return queryOptions({
    queryKey: queryKeys.snapshots.global(),
    queryFn: () => snapshotApi.getAllSnapshots(),
    staleTime: 2 * 60 * 1000,
    refetchInterval: false
  });
};
export const snapshotsForPathQueryOptions = (serverId: string | null, path: string | null, enabled: boolean = true) => {
  return queryOptions({
    queryKey: queryKeys.snapshots.forPath(serverId || "", path || ""),
    queryFn: () => snapshotApi.getAllSnapshots({
      server_id: serverId!,
      path: path!
    }),
    enabled: enabled && !!serverId && !!path,
    staleTime: 1 * 60 * 1000,
    refetchInterval: false
  });
};
export const backupRepositoryUsageQueryOptions = () => {
  return queryOptions({
    queryKey: queryKeys.snapshots.repositoryUsage(),
    queryFn: snapshotApi.getBackupRepositoryUsage,
    refetchInterval: 30000,
    staleTime: 15000,
    retry: (failureCount, error) => {
      // Restic-not-configured surfaces as a 500 with 'restic' in the message; don't hammer it.
      if (getErrorStatus(error) === 500 && error?.message?.includes('restic'))
        return false;
      return shouldRetryQuery(failureCount, error, 2);
    }
  });
};
export const snapshotLocksQueryOptions = (enabled: boolean = false) => {
  return queryOptions({
    queryKey: queryKeys.snapshots.locks(),
    queryFn: snapshotApi.listLocks,
    enabled,
    staleTime: 0,
    refetchInterval: false
  });
};
