import { useQueries, useQuery } from '@tanstack/react-query'
import {
  playerApi,
  type PlayerMapProfileResponse,
} from '@/hooks/api/playerApi'
import { queryKeys } from '@/utils/api'

function normalizeUuid(uuid: string | null | undefined): string | null {
  if (!uuid) return null
  const normalized = uuid.replaceAll('-', '').toLowerCase()
  if (!/^[0-9a-f]{32}$/.test(normalized)) return null
  return normalized
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

export const usePlayerMapProfiles = (
  uuids: readonly (string | null | undefined)[],
  enabled = true
) => {
  const normalizedUuids = Array.from(
    new Set(
      uuids
        .map((uuid) => normalizeUuid(uuid))
        .filter((uuid): uuid is string => !!uuid)
    )
  )
  const results = useQueries({
    queries: normalizedUuids.map((uuid) => ({
      queryKey: queryKeys.players.mapProfileByUUID(uuid),
      queryFn: () => playerApi.getPlayerMapProfile(uuid),
      enabled,
      staleTime: 10 * 60 * 1000,
      retry: false
    }))
  })
  const profilesByUuid = new Map<string, PlayerMapProfileResponse>()
  const pendingUuids = new Set<string>()
  results.forEach((result, index) => {
    const uuid = normalizedUuids[index]
    if (!uuid) return
    if (result.data) profilesByUuid.set(uuid, result.data)
    if (result.isLoading || result.isFetching) pendingUuids.add(uuid)
  })
  return { uuids: normalizedUuids, results, profilesByUuid, pendingUuids }
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
    usePlayerMapProfile,
    usePlayerMapProfiles,
    useServerOnlinePlayers,
    usePlayerSessions,
    usePlayerSessionStats,
    usePlayerChat,
    usePlayerAchievements
  }
}
