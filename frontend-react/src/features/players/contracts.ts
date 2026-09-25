
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

export interface PlayerMapProfileResponse {
  player_db_id: number | null
  uuid: string
  current_name: string | null
  avatar_base64: string | null
  resolved: boolean
  last_skin_update: string | null
}

export type PlayerMapProfilesStreamEvent =
  | {
      event_type: 'profile'
      profile: PlayerMapProfileResponse
    }
  | {
      event_type: 'complete'
      total: number
      resolved: number
    }
  | {
      event_type: 'error'
      message: string
    }

export type PlayerCleanupKind = 'offline_uuid' | 'ignored_name_prefix'

export interface PlayerCleanupCandidate {
  player_db_id: number
  uuid: string
  current_name: string
  first_seen: string
  last_seen: string | null
  session_count: number
  chat_message_count: number
  achievement_count: number
}

export interface PlayerCleanupPreviewResponse {
  kind: PlayerCleanupKind
  ignored_name_prefixes: string[]
  candidates: PlayerCleanupCandidate[]
}

export interface PlayerCleanupDeleteResponse {
  kind: PlayerCleanupKind
  deleted_count: number
  deleted_players: PlayerCleanupCandidate[]
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

export interface SessionStatsResponse {
  total_sessions: number
  total_playtime_seconds: number
  average_session_seconds: number
  longest_session_seconds: number
  sessions_by_server: Record<string, number>
  playtime_by_server: Record<string, number>
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
