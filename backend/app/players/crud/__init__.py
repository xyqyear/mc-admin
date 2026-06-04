"""CRUD operations for player management system."""

from .heartbeat import get_heartbeat, upsert_heartbeat
from .player import (
    get_all_player_names_with_ids,
    get_or_add_player_by_name,
    get_player_by_db_id,
    get_player_by_name,
    get_player_by_uuid,
    get_players_by_uuids,
    update_player_skin,
    upsert_player,
    upsert_player_profile,
)
from .player_cleanup import (
    PlayerCleanupCandidate,
    PlayerCleanupDeleteResponse,
    PlayerCleanupKind,
    PlayerCleanupPreviewResponse,
    delete_player_cleanup_candidates,
    get_player_cleanup_preview,
)
from .player_achievement import upsert_achievement
from .player_chat import create_chat_message
from .player_session import (
    end_all_open_sessions,
    end_all_open_sessions_on_server,
    get_all_open_sessions_on_server,
    get_online_player_names_on_server,
    get_online_players_with_names_grouped_by_server,
    get_or_create_session,
)

__all__ = [
    # Heartbeat
    "upsert_heartbeat",
    "get_heartbeat",
    # Player
    "upsert_player",
    "get_player_by_name",
    "get_player_by_uuid",
    "get_players_by_uuids",
    "get_player_by_db_id",
    "get_all_player_names_with_ids",
    "get_or_add_player_by_name",
    "update_player_skin",
    "upsert_player_profile",
    "PlayerCleanupCandidate",
    "PlayerCleanupDeleteResponse",
    "PlayerCleanupKind",
    "PlayerCleanupPreviewResponse",
    "delete_player_cleanup_candidates",
    "get_player_cleanup_preview",
    # Player Session
    "get_or_create_session",
    "end_all_open_sessions",
    "get_all_open_sessions_on_server",
    "end_all_open_sessions_on_server",
    "get_online_players_with_names_grouped_by_server",
    "get_online_player_names_on_server",
    # Player Chat
    "create_chat_message",
    # Player Achievement
    "upsert_achievement",
]
