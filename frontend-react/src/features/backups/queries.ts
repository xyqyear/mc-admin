import { queryOptions } from '@tanstack/react-query';
import { getErrorStatus, shouldRetryQuery } from '@/shared/http/api';
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from 'react';
import { useServerInfo } from '@/features/servers/queries';
import { snapshotApi } from "@/features/backups/api";
import { queryKeys } from "@/shared/http/api";
import type { PathsScope, RestorationFilters, SnapshotScope, WorldScope } from './contracts';
import { activeRestorationsQueryOptions, retainActiveRestorationPolling } from './activeRestorationPolling';
import { checkLogicalSnapshotPaths } from './targetRules';

export function snapshotRulesQueryOptions(serverId: string) {
  return queryOptions({
    queryKey: queryKeys.snapshots.rules(serverId),
    queryFn: ({ signal }) => snapshotApi.targetRules(serverId, signal),
    enabled: !!serverId,
    staleTime: Infinity,
    refetchOnMount: false,
    refetchOnWindowFocus: false,
    refetchOnReconnect: 'always',
    refetchInterval: false,
  });
}

export function useSnapshotRules(serverId: string, refreshOnEntry = false) {
  const client = useQueryClient();
  const identity = useServerInfo(serverId, { enabled: refreshOnEntry && !!serverId, refetchOnMount: false, refetchOnReconnect: refreshOnEntry ? 'always' : false });
  const generation = identity.data?.serverGeneration;
  const options = snapshotRulesQueryOptions(serverId);
  const updates = () => client.getQueryState(options.queryKey)?.dataUpdateCount ?? 0;
  const [entry, setEntry] = useState(() => ({ serverId, dataUpdateCount: updates() }));
  if (entry.serverId !== serverId) setEntry({ serverId, dataUpdateCount: updates() });
  const query = useQuery(options);
  const refetch = query.refetch;
  const refetchIdentity = identity.refetch;
  useEffect(() => {
    if (refreshOnEntry && serverId) {
      void refetchIdentity({ cancelRefetch: false });
      void refetch({ cancelRefetch: false });
    }
  }, [refreshOnEntry, serverId, refetch, refetchIdentity]);
  const previousGeneration = useRef({ serverId, generation });
  useEffect(() => {
    const previous = previousGeneration.current;
    previousGeneration.current = { serverId, generation };
    if (refreshOnEntry && previous.serverId === serverId && previous.generation != null && generation != null && previous.generation !== generation) {
      void refetch({ cancelRefetch: false });
    }
  }, [refreshOnEntry, serverId, generation, refetch]);
  const checked = !refreshOnEntry || (entry.serverId === serverId && updates() > entry.dataUpdateCount);
  const bound = generation != null && identity.data?.id === serverId && query.data?.server_id === serverId && query.data.server_generation === generation;
  return { ...query, isError: query.isError || identity.isError, checking: !checked || query.isFetching || !query.isSuccess || !bound || identity.isError };
}

export function useSnapshotTarget(scope: PathsScope | WorldScope | null) {
  const paths = scope?.kind === 'paths' ? scope : null;
  const world = scope?.kind === 'world' ? scope : null;
  const rules = useSnapshotRules(paths?.server_id ?? '');
  const target = useQuery({
    queryKey: queryKeys.snapshots.target(world),
    queryFn: () => snapshotApi.checkWorldTarget(world!),
    enabled: !!world,
    staleTime: 5000,
  });
  if (!paths) return target;
  return {
    ...rules,
    data: rules.checking || !rules.data ? undefined : checkLogicalSnapshotPaths(paths.paths, rules.data.ignored_paths),
    isPending: rules.checking && !rules.isError,
    isLoading: rules.checking && !rules.isError,
  };
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
