import { useEffect, useMemo, useState } from 'react'
import {
  useQuery,
  useQueryClient,
} from '@tanstack/react-query'
import {
  playerApi,
  type PlayerCleanupKind,
  type PlayerMapProfilesStreamEvent,
  type PlayerMapProfileResponse,
} from '@/hooks/api/playerApi'
import { queryKeys } from '@/utils/api'
import { readEventStream } from '@/utils/eventStream'

function normalizeUuid(uuid: string | null | undefined): string | null {
  if (!uuid) return null
  const normalized = uuid.replaceAll('-', '').toLowerCase()
  if (!/^[0-9a-f]{32}$/.test(normalized)) return null
  return normalized
}

function normalizeUuidList(
  uuids: readonly (string | null | undefined)[]
): string[] {
  return Array.from(
    new Set(
      uuids
        .map((uuid) => normalizeUuid(uuid))
        .filter((uuid): uuid is string => !!uuid)
    )
  )
}

export const useAllPlayers = (params?: {
  online_only?: boolean
  server_id?: string
}) => {
  return useQuery({
    queryKey: queryKeys.players.list(params),
    queryFn: () => playerApi.getAllPlayers(params),
    staleTime: 30 * 1000,
    refetchInterval: 30 * 1000,
    retry: 2
  })
}

export const usePlayerByUUID = (uuid: string | null) => {
  return useQuery({
    queryKey: queryKeys.players.detailByUUID(uuid!),
    queryFn: () => playerApi.getPlayerByUUID(uuid!),
    enabled: !!uuid,
    staleTime: 1 * 60 * 1000,
    retry: 2
  })
}

export const usePlayerMapProfile = (uuid: string | null) => {
  const normalized = normalizeUuid(uuid)
  return useQuery({
    queryKey: queryKeys.players.mapProfileByUUID(normalized ?? ''),
    queryFn: () => playerApi.getPlayerMapProfile(normalized!),
    enabled: !!normalized,
    staleTime: 10 * 60 * 1000,
    retry: false
  })
}

export const usePlayerCleanupPreview = (
  kind: PlayerCleanupKind | null,
  enabled: boolean
) => {
  return useQuery({
    queryKey: queryKeys.players.cleanupPreview(kind),
    queryFn: () => playerApi.getPlayerCleanupPreview(kind!),
    enabled: !!kind && enabled,
    staleTime: 0,
    retry: 1
  })
}

export const usePlayerMapProfiles = (
  uuids: readonly (string | null | undefined)[],
  enabled = true
) => {
  const queryClient = useQueryClient()
  const normalizedUuidKey = normalizeUuidList(uuids).join('\0')
  const normalizedUuids = useMemo(
    () => (normalizedUuidKey ? normalizedUuidKey.split('\0') : []),
    [normalizedUuidKey]
  )
  const [profilesByUuid, setProfilesByUuid] = useState<
    Map<string, PlayerMapProfileResponse>
  >(new Map())
  const [pendingUuids, setPendingUuids] = useState<Set<string>>(new Set())
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const cachedProfiles = new Map<string, PlayerMapProfileResponse>()
    for (const uuid of normalizedUuids) {
      const cached = queryClient.getQueryData<PlayerMapProfileResponse>(
        queryKeys.players.mapProfileByUUID(uuid)
      )
      if (cached) cachedProfiles.set(uuid, cached)
    }

    setProfilesByUuid(cachedProfiles)
    setPendingUuids(
      enabled
        ? new Set(normalizedUuids.filter((uuid) => !cachedProfiles.has(uuid)))
        : new Set()
    )
    setError(null)

    if (!enabled || normalizedUuids.length === 0) return

    const ctrl = new AbortController()

    void readEventStream<PlayerMapProfilesStreamEvent>({
      url: '/players/profiles/stream',
      method: 'POST',
      body: { uuids: normalizedUuids },
      signal: ctrl.signal,
      onEvent: (event) => {
        if (event.event_type === 'profile') {
          const uuid = normalizeUuid(event.profile.uuid)
          if (!uuid) return
          const profile = { ...event.profile, uuid }
          queryClient.setQueryData(
            queryKeys.players.mapProfileByUUID(uuid),
            profile
          )
          setProfilesByUuid((prev) => {
            const next = new Map(prev)
            next.set(uuid, profile)
            return next
          })
          setPendingUuids((prev) => {
            if (!prev.has(uuid)) return prev
            const next = new Set(prev)
            next.delete(uuid)
            return next
          })
          return
        }
        if (event.event_type === 'complete') {
          setPendingUuids(new Set())
          return
        }
        if (event.event_type === 'error') {
          setError(event.message)
          setPendingUuids(new Set())
        }
      },
      onClose: () => {
        setPendingUuids(new Set())
      },
      onError: (message) => {
        setError(message)
        setPendingUuids(new Set())
      },
    })

    return () => {
      ctrl.abort()
    }
  }, [enabled, normalizedUuids, queryClient])

  return {
    uuids: normalizedUuids,
    profilesByUuid,
    pendingUuids,
    error,
    isLoading: enabled && pendingUuids.size > 0 && profilesByUuid.size === 0,
    isFetching: enabled && pendingUuids.size > 0,
    isError: !!error,
  }
}

export const useServerOnlinePlayers = (serverId: string) => {
  return useQuery({
    queryKey: queryKeys.players.serverOnline(serverId),
    queryFn: () => playerApi.getServerOnlinePlayers(serverId),
    staleTime: 10 * 1000,
    refetchInterval: 10 * 1000,
    retry: 2
  })
}

export const usePlayerSessions = (
  playerDbId: number | null,
  params?: {
    limit?: number
    server_id?: string
    start_date?: string
    end_date?: string
  }
) => {
  return useQuery({
    queryKey: queryKeys.players.sessions(playerDbId!, params),
    queryFn: () => playerApi.getPlayerSessions(playerDbId!, params),
    enabled: !!playerDbId,
    staleTime: 2 * 60 * 1000,
    retry: 2
  })
}

export const usePlayerSessionStats = (
  playerDbId: number | null,
  period: 'all' | 'week' | 'month' | 'year' = 'all'
) => {
  return useQuery({
    queryKey: queryKeys.players.sessionStats(playerDbId!, period),
    queryFn: () => playerApi.getPlayerSessionStats(playerDbId!, period),
    enabled: !!playerDbId,
    staleTime: 5 * 60 * 1000,
    retry: 2
  })
}

export const usePlayerChat = (
  playerDbId: number | null,
  params?: {
    limit?: number
    server_id?: string
    search?: string
    start_date?: string
    end_date?: string
  }
) => {
  return useQuery({
    queryKey: queryKeys.players.chat(playerDbId!, params),
    queryFn: () => playerApi.getPlayerChat(playerDbId!, params),
    enabled: !!playerDbId,
    staleTime: 1 * 60 * 1000,
    retry: 2
  })
}

export const usePlayerAchievements = (
  playerDbId: number | null,
  serverId?: string
) => {
  return useQuery({
    queryKey: queryKeys.players.achievements(playerDbId!, serverId),
    queryFn: () => playerApi.getPlayerAchievements(playerDbId!, serverId),
    enabled: !!playerDbId,
    staleTime: 5 * 60 * 1000,
    retry: 2
  })
}

export const usePlayerQueries = () => {
  return {
    useAllPlayers,
    usePlayerByUUID,
    usePlayerCleanupPreview,
    usePlayerMapProfile,
    usePlayerMapProfiles,
    useServerOnlinePlayers,
    usePlayerSessions,
    usePlayerSessionStats,
    usePlayerChat,
    usePlayerAchievements
  }
}
