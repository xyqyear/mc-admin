import { useQuery } from '@tanstack/react-query'
import { playerApi } from '@/hooks/api/playerApi'
import { queryKeys } from '@/utils/api'

// Query for getting all players with optional filters
export const useAllPlayers = (params?: {
  online_only?: boolean
  server_id?: string
}) => {
  return useQuery({
    queryKey: queryKeys.players.list(params),
    queryFn: () => playerApi.getAllPlayers(params),
    staleTime: 30 * 1000, // 30 seconds - player list changes moderately
    refetchInterval: 30 * 1000, // Auto-refresh every 30 seconds
    retry: 2
  })
}

// Query for getting player detail by UUID
export const usePlayerByUUID = (uuid: string | null) => {
  return useQuery({
    queryKey: queryKeys.players.detailByUUID(uuid!),
    queryFn: () => playerApi.getPlayerByUUID(uuid!),
    enabled: !!uuid,
    staleTime: 1 * 60 * 1000, // 1 minute - player details change occasionally
    retry: 2
  })
}

// Query for getting player detail by name
export const usePlayerByName = (name: string | null) => {
  return useQuery({
    queryKey: queryKeys.players.detailByName(name!),
    queryFn: () => playerApi.getPlayerByName(name!),
    enabled: !!name,
    staleTime: 1 * 60 * 1000, // 1 minute - player details change occasionally
    retry: 2
  })
}

// Query for getting server online players
export const useServerOnlinePlayers = (serverId: string) => {
  return useQuery({
    queryKey: queryKeys.players.serverOnline(serverId),
    queryFn: () => playerApi.getServerOnlinePlayers(serverId),
    staleTime: 10 * 1000, // 10 seconds - online players change frequently
    refetchInterval: 10 * 1000, // Auto-refresh every 10 seconds
    retry: 2
  })
}

// Query for getting player sessions
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
    staleTime: 2 * 60 * 1000, // 2 minutes - session history changes occasionally
    retry: 2
  })
}

// Query for getting player session statistics
export const usePlayerSessionStats = (
  playerDbId: number | null,
  period: 'all' | 'week' | 'month' | 'year' = 'all'
) => {
  return useQuery({
    queryKey: queryKeys.players.sessionStats(playerDbId!, period),
    queryFn: () => playerApi.getPlayerSessionStats(playerDbId!, period),
    enabled: !!playerDbId,
    staleTime: 5 * 60 * 1000, // 5 minutes - statistics change less frequently
    retry: 2
  })
}

// Query for getting player chat history
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
    staleTime: 1 * 60 * 1000, // 1 minute - chat history changes occasionally
    retry: 2
  })
}

// Query for getting player achievements
export const usePlayerAchievements = (
  playerDbId: number | null,
  serverId?: string
) => {
  return useQuery({
    queryKey: queryKeys.players.achievements(playerDbId!, serverId),
    queryFn: () => playerApi.getPlayerAchievements(playerDbId!, serverId),
    enabled: !!playerDbId,
    staleTime: 5 * 60 * 1000, // 5 minutes - achievements change less frequently
    retry: 2
  })
}

// Combined hook for player queries (used in detail views)
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
