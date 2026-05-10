import { useQuery } from '@tanstack/react-query'
import { playerApi } from '@/hooks/api/playerApi'
import { queryKeys } from '@/utils/api'

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

export const usePlayerByName = (name: string | null) => {
  return useQuery({
    queryKey: queryKeys.players.detailByName(name!),
    queryFn: () => playerApi.getPlayerByName(name!),
    enabled: !!name,
    staleTime: 1 * 60 * 1000,
    retry: 2
  })
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
    usePlayerByName,
    useServerOnlinePlayers,
    usePlayerSessions,
    usePlayerSessionStats,
    usePlayerChat,
    usePlayerAchievements
  }
}
