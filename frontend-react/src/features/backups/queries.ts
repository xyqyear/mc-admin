import { queryOptions } from '@tanstack/react-query';
import { getErrorStatus, shouldRetryQuery } from '@/shared/http/api';
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from 'react';
import { snapshotApi } from "@/features/backups/api";
import { queryKeys } from "@/shared/http/api";
import type { RestorationFilters, SnapshotScope } from './contracts';
import { activeRestorationsQueryOptions, retainActiveRestorationPolling } from './activeRestorationPolling';

export function useSnapshotTarget(scope: SnapshotScope | null) {
  return useQuery({
    queryKey: queryKeys.snapshots.target(scope),
    queryFn: () => snapshotApi.checkTarget(scope!),
    enabled: !!scope,
    staleTime: 5000,
  });
}

export function useActiveRestorations(serverId?: string, enabled = true) {
  const client = useQueryClient();
  const options = activeRestorationsQueryOptions(serverId);
  const updates = () => client.getQueryState(options.queryKey)?.dataUpdateCount ?? 0;
  const [entry, setEntry] = useState(() => ({ serverId, enabled, dataUpdateCount: updates() }));
  if (entry.serverId !== serverId || entry.enabled !== enabled) {
    setEntry({ serverId, enabled, dataUpdateCount: updates() });
  }
  const query = useQuery({
    ...options,
    enabled,
    staleTime: Infinity,
    refetchOnMount: false,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    refetchInterval: false,
  });
  useEffect(() => {
    if (!enabled) return;
    const polling = retainActiveRestorationPolling(client, serverId);
    void polling.refresh();
    return polling.release;
  }, [client, serverId, enabled]);
  const checked = entry.serverId === serverId && entry.enabled === enabled && updates() > entry.dataUpdateCount;
  return { ...query, checking: enabled && (!checked || !query.isSuccess) };
}

export function useEligibleSnapshots(scope: SnapshotScope | null) {
  return useQuery({
    queryKey: queryKeys.snapshots.eligible(scope),
    queryFn: () => snapshotApi.eligible(scope!),
    enabled: !!scope,
    staleTime: 5000,
  });
}

export function useRestorationHistory(serverId?: string, offset = 0, enabled = true, filters: RestorationFilters = {}) {
  return useQuery({
    queryKey: queryKeys.snapshots.history(serverId, offset, filters),
    queryFn: () => snapshotApi.history(serverId, offset, filters),
    enabled,
    refetchInterval: false,
    refetchOnMount: 'always',
    staleTime: 0,
  });
}
export const useGlobalSnapshots = (options?: Partial<Omit<ReturnType<typeof globalSnapshotsQueryOptions>, 'queryKey' | 'queryFn'>>) => {
  return useQuery({ ...globalSnapshotsQueryOptions(), ...options });
};

export const useSnapshotsForPath = (serverId: string | null, path: string | null, enabled: boolean = true, options?: Partial<Omit<ReturnType<typeof snapshotsForPathQueryOptions>, 'queryKey' | 'queryFn'>>) => {
  return useQuery({ ...snapshotsForPathQueryOptions(serverId, path, enabled), ...options });
};

export const useBackupRepositoryUsage = (options?: Partial<Omit<ReturnType<typeof backupRepositoryUsageQueryOptions>, 'queryKey' | 'queryFn'>>) => {
  return useQuery({ ...backupRepositoryUsageQueryOptions(), ...options });
};

export const useSnapshotLocks = (enabled: boolean = false, options?: Partial<Omit<ReturnType<typeof snapshotLocksQueryOptions>, 'queryKey' | 'queryFn'>>) => {
  return useQuery({ ...snapshotLocksQueryOptions(enabled), ...options });
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
