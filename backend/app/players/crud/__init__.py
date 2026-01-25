"""CRUD operations for player management system."""

from .heartbeat import get_heartbeat, upsert_heartbeat
from .player import (
    get_all_player_names_with_ids,
    get_or_add_player_by_name,
    get_player_by_name,
    update_player_skin,
    upsert_player,
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
    "get_all_player_names_with_ids",
    "get_or_add_player_by_name",
    "update_player_skin",
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
