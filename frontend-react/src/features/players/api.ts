import { api } from '@/shared/http/api';
import type { PlayerSummary, PlayerDetailResponse, OnlinePlayerInfo, PlayerMapProfileResponse, PlayerCleanupKind, PlayerCleanupPreviewResponse, PlayerCleanupDeleteResponse, SessionInfo, SessionStatsResponse, ChatMessageInfo, AchievementInfo } from '@/features/players/contracts';


export const playerApi = {
  getAllPlayers: async (params?: {
    online_only?: boolean
    server_id?: string
  }): Promise<PlayerSummary[]> => {
    const searchParams = new URLSearchParams()

    if (params?.online_only !== undefined) {
      searchParams.append('online_only', String(params.online_only))
    }

    if (params?.server_id) {
      searchParams.append('server_id', params.server_id)
    }

    const queryString = searchParams.toString()
    const url = queryString ? `/players/?${queryString}` : '/players/'

    const response = await api.get(url)
    return response.data
  },

  getPlayerByUUID: async (uuid: string): Promise<PlayerDetailResponse> => {
    const response = await api.get(`/players/uuid/${uuid}`)
    return response.data
  },

  getPlayerMapProfile: async (uuid: string): Promise<PlayerMapProfileResponse> => {
    const response = await api.get(`/players/uuid/${uuid}/profile`)
    return response.data
  },

  refreshPlayerSkin: async (playerDbId: number): Promise<{ message: string }> => {
    const response = await api.post(`/players/${playerDbId}/refresh-skin`)
    return response.data
  },

  getPlayerCleanupPreview: async (
    kind: PlayerCleanupKind
  ): Promise<PlayerCleanupPreviewResponse> => {
    const response = await api.get(`/players/cleanup/${kind}/preview`)
    return response.data
  },

  deletePlayerCleanup: async (
    kind: PlayerCleanupKind
  ): Promise<PlayerCleanupDeleteResponse> => {
    const response = await api.delete(`/players/cleanup/${kind}`)
    return response.data
  },

  getPlayerSessions: async (
    playerDbId: number,
    params?: {
      limit?: number
      server_id?: string
      start_date?: string
      end_date?: string
    }
  ): Promise<SessionInfo[]> => {
    const searchParams = new URLSearchParams()

    if (params?.limit !== undefined) {
      searchParams.append('limit', String(params.limit))
    }

    if (params?.server_id) {
      searchParams.append('server_id', params.server_id)
    }

    if (params?.start_date) {
      searchParams.append('start_date', params.start_date)
    }

    if (params?.end_date) {
      searchParams.append('end_date', params.end_date)
    }

    const queryString = searchParams.toString()
    const url = queryString
      ? `/players/${playerDbId}/sessions?${queryString}`
      : `/players/${playerDbId}/sessions`

    const response = await api.get(url)
    return response.data
  },

  getPlayerSessionStats: async (
    playerDbId: number,
    period: 'all' | 'week' | 'month' | 'year' = 'all'
  ): Promise<SessionStatsResponse> => {
    const response = await api.get(`/players/${playerDbId}/sessions/stats`, {
      params: { period }
    })
    return response.data
  },

  getServerOnlinePlayers: async (serverId: string): Promise<OnlinePlayerInfo[]> => {
    const response = await api.get(`/servers/${serverId}/online-players`)
    return response.data
  },

  getPlayerChat: async (
    playerDbId: number,
    params?: {
      limit?: number
      server_id?: string
      search?: string
      start_date?: string
      end_date?: string
    }
  ): Promise<ChatMessageInfo[]> => {
    const searchParams = new URLSearchParams()

    if (params?.limit !== undefined) {
      searchParams.append('limit', String(params.limit))
    }

    if (params?.server_id) {
      searchParams.append('server_id', params.server_id)
    }

    if (params?.search) {
      searchParams.append('search', params.search)
    }

    if (params?.start_date) {
      searchParams.append('start_date', params.start_date)
    }

    if (params?.end_date) {
      searchParams.append('end_date', params.end_date)
    }

    const queryString = searchParams.toString()
    const url = queryString
      ? `/players/${playerDbId}/chat?${queryString}`
      : `/players/${playerDbId}/chat`

    const response = await api.get(url)
    return response.data
  },

  getPlayerAchievements: async (
    playerDbId: number,
    serverId?: string
  ): Promise<AchievementInfo[]> => {
    const searchParams = new URLSearchParams()

    if (serverId) {
      searchParams.append('server_id', serverId)
    }

    const queryString = searchParams.toString()
    const url = queryString
      ? `/players/${playerDbId}/achievements?${queryString}`
      : `/players/${playerDbId}/achievements`

    const response = await api.get(url)
    return response.data
  }
}