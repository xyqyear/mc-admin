import { queryOptions } from '@tanstack/react-query';
import { shouldRetryQuery } from '@/shared/http/api';
import { useEffect, useMemo, useState } from 'react';
import { useQuery, useQueries, useQueryClient, } from '@tanstack/react-query';
import { playerApi } from '@/features/players/api';
import type { PlayerCleanupKind, PlayerMapProfilesStreamEvent, PlayerMapProfileResponse } from '@/features/players/contracts';
import { queryKeys } from '@/shared/http/api';
import { readEventStream } from '@/shared/http/eventStream';
function normalizeUuid(uuid: string | null | undefined): string | null {
  if (!uuid)
    return null;
  const normalized = uuid.replaceAll('-', '').toLowerCase();
  if (!/^[0-9a-f]{32}$/.test(normalized))
    return null;
  return normalized;
}
function normalizeUuidList(uuids: readonly (string | null | undefined)[]): string[] {
  return Array.from(new Set(uuids
    .map((uuid) => normalizeUuid(uuid))
    .filter((uuid): uuid is string => !!uuid)));
}
function combineMapProfiles(results: readonly { data: PlayerMapProfileResponse | undefined }[]) {
  return results.map((result) => result.data);
}
export const useAllPlayers = (params?: {
  online_only?: boolean;
  server_id?: string;
}) => {
  return useQuery({ ...allPlayersQueryOptions(params) });
};
export const usePlayerByUUID = (uuid: string | null) => {
  return useQuery({ ...playerByUUIDQueryOptions(uuid) });
};
export const usePlayerMapProfile = (uuid: string | null) => {
  return useQuery({ ...playerMapProfileQueryOptions(uuid) });
};
export const usePlayerCleanupPreview = (kind: PlayerCleanupKind | null, enabled: boolean) => {
  return useQuery({ ...playerCleanupPreviewQueryOptions(kind, enabled) });
};
export const usePlayerMapProfiles = (uuids: readonly (string | null | undefined)[], enabled = true) => {
  const queryClient = useQueryClient();
  const normalizedUuidKey = normalizeUuidList(uuids).join('\0');
  const normalizedUuids = useMemo(() => (normalizedUuidKey ? normalizedUuidKey.split('\0') : []), [normalizedUuidKey]);
  const profiles = useQueries({
    queries: normalizedUuids.map((uuid) => ({ ...playerMapProfileQueryOptions(uuid), enabled: false })),
    combine: combineMapProfiles,
  });
  const profilesByUuid = useMemo(() => new Map(normalizedUuids.flatMap((uuid, index) => {
    const profile = profiles[index];
    return profile ? [[uuid, profile] as const] : [];
  })), [normalizedUuids, profiles]);
  const [pendingUuids, setPendingUuids] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    const cachedProfiles = new Map<string, PlayerMapProfileResponse>();
    for (const uuid of normalizedUuids) {
      const cached = queryClient.getQueryData<PlayerMapProfileResponse>(queryKeys.players.mapProfileByUUID(uuid));
      if (cached)
        cachedProfiles.set(uuid, cached);
    }
    setPendingUuids(enabled
      ? new Set(normalizedUuids.filter((uuid) => !cachedProfiles.has(uuid)))
      : new Set());
    setError(null);
    if (!enabled || normalizedUuids.length === 0)
      return;
    const ctrl = new AbortController();
    void readEventStream<PlayerMapProfilesStreamEvent>({
      url: '/players/profiles/stream',
      method: 'POST',
      body: { uuids: normalizedUuids },
      signal: ctrl.signal,
      onEvent: (event) => {
        if (event.event_type === 'profile') {
          const uuid = normalizeUuid(event.profile.uuid);
          if (!uuid)
            return;
          const profile = { ...event.profile, uuid };
          queryClient.setQueryData(queryKeys.players.mapProfileByUUID(uuid), profile);
          setPendingUuids((prev) => {
            if (!prev.has(uuid))
              return prev;
            const next = new Set(prev);
            next.delete(uuid);
            return next;
          });
          return;
        }
        if (event.event_type === 'complete') {
          setPendingUuids(new Set());
          return;
        }
        if (event.event_type === 'error') {
          setError(event.message);
          setPendingUuids(new Set());
        }
      },
      onClose: () => {
        setPendingUuids(new Set());
      },
      onError: (message) => {
        setError(message);
        setPendingUuids(new Set());
      },
    });
    return () => {
      ctrl.abort();
    };
  }, [enabled, normalizedUuids, queryClient]);
  return {
    uuids: normalizedUuids,
    profilesByUuid,
    pendingUuids,
    error,
    isLoading: enabled && pendingUuids.size > 0 && profilesByUuid.size === 0,
    isFetching: enabled && pendingUuids.size > 0,
    isError: !!error,
  };
};
export const useServerOnlinePlayers = (serverId: string) => {
  return useQuery({ ...serverOnlinePlayersQueryOptions(serverId) });
};
export const usePlayerSessions = (playerDbId: number | null, params?: {
  limit?: number;
  server_id?: string;
  start_date?: string;
  end_date?: string;
}) => {
  return useQuery({ ...playerSessionsQueryOptions(playerDbId, params) });
};
export const usePlayerSessionStats = (playerDbId: number | null, period: 'all' | 'week' | 'month' | 'year' = 'all') => {
  return useQuery({ ...playerSessionStatsQueryOptions(playerDbId, period) });
};
export const usePlayerChat = (playerDbId: number | null, params?: {
  limit?: number;
  server_id?: string;
  search?: string;
  start_date?: string;
  end_date?: string;
}) => {
  return useQuery({ ...playerChatQueryOptions(playerDbId, params) });
};
export const usePlayerAchievements = (playerDbId: number | null, serverId?: string) => {
  return useQuery({ ...playerAchievementsQueryOptions(playerDbId, serverId) });
};
export const allPlayersQueryOptions = (params?: {
  online_only?: boolean;
  server_id?: string;
}) => {
  return queryOptions({
    queryKey: queryKeys.players.list(params),
    queryFn: () => playerApi.getAllPlayers(params),
    staleTime: 30 * 1000,
    refetchInterval: 30 * 1000,
    retry: (failureCount, error) => shouldRetryQuery(failureCount, error, 2)
  });
};
export const playerByUUIDQueryOptions = (uuid: string | null) => {
  return queryOptions({
    queryKey: queryKeys.players.detailByUUID(uuid!),
    queryFn: () => playerApi.getPlayerByUUID(uuid!),
    enabled: !!uuid,
    staleTime: 1 * 60 * 1000,
    retry: (failureCount, error) => shouldRetryQuery(failureCount, error, 2)
  });
};
export const playerMapProfileQueryOptions = (uuid: string | null) => {
  const normalized = normalizeUuid(uuid);
  return queryOptions({
    queryKey: queryKeys.players.mapProfileByUUID(normalized ?? ''),
    queryFn: () => playerApi.getPlayerMapProfile(normalized!),
    enabled: !!normalized,
    staleTime: 10 * 60 * 1000,
    retry: false
  });
};
export const playerCleanupPreviewQueryOptions = (kind: PlayerCleanupKind | null, enabled: boolean) => {
  return queryOptions({
    queryKey: queryKeys.players.cleanupPreview(kind),
    queryFn: () => playerApi.getPlayerCleanupPreview(kind!),
    enabled: !!kind && enabled,
    staleTime: 0,
    retry: (failureCount, error) => shouldRetryQuery(failureCount, error, 1)
  });
};
export const serverOnlinePlayersQueryOptions = (serverId: string) => {
  return queryOptions({
    queryKey: queryKeys.players.serverOnline(serverId),
    queryFn: () => playerApi.getServerOnlinePlayers(serverId),
    staleTime: 10 * 1000,
    refetchInterval: 10 * 1000,
    retry: (failureCount, error) => shouldRetryQuery(failureCount, error, 2)
  });
};
export const playerSessionsQueryOptions = (playerDbId: number | null, params?: {
  limit?: number;
  server_id?: string;
  start_date?: string;
  end_date?: string;
}) => {
  return queryOptions({
    queryKey: queryKeys.players.sessions(playerDbId!, params),
    queryFn: () => playerApi.getPlayerSessions(playerDbId!, params),
    enabled: !!playerDbId,
    staleTime: 2 * 60 * 1000,
    retry: (failureCount, error) => shouldRetryQuery(failureCount, error, 2)
  });
};
export const playerSessionStatsQueryOptions = (playerDbId: number | null, period: 'all' | 'week' | 'month' | 'year' = 'all') => {
  return queryOptions({
    queryKey: queryKeys.players.sessionStats(playerDbId!, period),
    queryFn: () => playerApi.getPlayerSessionStats(playerDbId!, period),
    enabled: !!playerDbId,
    staleTime: 5 * 60 * 1000,
    retry: (failureCount, error) => shouldRetryQuery(failureCount, error, 2)
  });
};
export const playerChatQueryOptions = (playerDbId: number | null, params?: {
  limit?: number;
  server_id?: string;
  search?: string;
  start_date?: string;
  end_date?: string;
}) => {
  return queryOptions({
    queryKey: queryKeys.players.chat(playerDbId!, params),
    queryFn: () => playerApi.getPlayerChat(playerDbId!, params),
    enabled: !!playerDbId,
    staleTime: 1 * 60 * 1000,
    retry: (failureCount, error) => shouldRetryQuery(failureCount, error, 2)
  });
};
export const playerAchievementsQueryOptions = (playerDbId: number | null, serverId?: string) => {
  return queryOptions({
    queryKey: queryKeys.players.achievements(playerDbId!, serverId),
    queryFn: () => playerApi.getPlayerAchievements(playerDbId!, serverId),
    enabled: !!playerDbId,
    staleTime: 5 * 60 * 1000,
    retry: (failureCount, error) => shouldRetryQuery(failureCount, error, 2)
  });
};
