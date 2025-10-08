import { api } from '@/utils/api'

// Types based on backend API response models
export interface PlayerSummary {
  player_db_id: number
  uuid: string
  current_name: string
  avatar_base64: string | null
  is_online: boolean
  last_seen: string | null
  total_playtime_seconds: number
  first_seen: string
}

export interface PlayerDetailResponse {
  player_db_id: number
  uuid: string
  current_name: string
  skin_base64: string | null
  avatar_base64: string | null
  is_online: boolean
  current_servers: string[]
  last_seen: string | null
  first_seen: string
  total_playtime_seconds: number
  total_sessions: number
  total_messages: number
  total_achievements: number
}

export interface OnlinePlayerInfo {
  player_db_id: number
  uuid: string
  current_name: string
  avatar_base64: string | null
  joined_at: string
  session_duration_seconds: number
}

export interface SessionInfo {
  session_id: number
  server_db_id: number
  server_id: string
  joined_at: string
  left_at: string | null
  duration_seconds: number | null
  is_active: boolean
}

export interface DailyPlaytime {
  date: string
  seconds: number
}

export interface SessionStatsResponse {
  total_sessions: number
  total_playtime_seconds: number
  average_session_seconds: number
  longest_session_seconds: number
  sessions_by_server: Record<string, number>
  playtime_by_server: Record<string, number>
  daily_playtime: DailyPlaytime[]
}

export interface ChatMessageInfo {
  message_id: number
  server_db_id: number
  server_id: string
  message_text: string
  sent_at: string
}

export interface AchievementInfo {
  achievement_id: number
  server_db_id: number
  server_id: string
  achievement_name: string
  earned_at: string
}

// API functions
export const playerApi = {
  // Get all players summary with optional filters
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

  // Get player detail by UUID
  getPlayerByUUID: async (uuid: string): Promise<PlayerDetailResponse> => {
    const response = await api.get(`/players/uuid/${uuid}`)
    return response.data
  },

  // Get player detail by name
  getPlayerByName: async (name: string): Promise<PlayerDetailResponse> => {
    const response = await api.get(`/players/name/${name}`)
    return response.data
  },

  // Get player avatar image URL
  getPlayerAvatarUrl: (playerDbId: number): string => {
    return `/players/${playerDbId}/avatar`
  },

  // Get player skin image URL
  getPlayerSkinUrl: (playerDbId: number): string => {
    return `/players/${playerDbId}/skin`
  },

  // Refresh player skin
  refreshPlayerSkin: async (playerDbId: number): Promise<{ message: string }> => {
    const response = await api.post(`/players/${playerDbId}/refresh-skin`)
    return response.data
  },

  // Get player sessions
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

  // Get player session statistics
  getPlayerSessionStats: async (
    playerDbId: number,
    period: 'all' | 'week' | 'month' | 'year' = 'all'
  ): Promise<SessionStatsResponse> => {
    const response = await api.get(`/players/${playerDbId}/sessions/stats`, {
      params: { period }
    })
    return response.data
  },

  // Get server online players
  getServerOnlinePlayers: async (serverId: string): Promise<OnlinePlayerInfo[]> => {
    const response = await api.get(`/servers/${serverId}/online-players`)
    return response.data
  },

  // Get player chat history
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

  // Get player achievements
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
