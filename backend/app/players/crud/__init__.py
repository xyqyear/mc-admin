"""CRUD operations for player management system."""

from .heartbeat import get_heartbeat, upsert_heartbeat
from .player import (
    get_or_add_player_by_name,
    get_player_by_name,
    update_player_last_seen,
    update_player_skin,
    upsert_player,
)
from .player_achievement import upsert_achievement
from .player_chat import create_chat_message
from .player_online_status import (
    get_online_players_grouped_by_server,
    get_online_players_on_server,
    set_all_players_offline_on_server,
    set_player_offline,
    upsert_player_online_status,
)
from .player_session import (
    create_session,
    end_session,
    get_all_open_sessions_on_server,
    get_open_session,
)

__all__ = [
    # Heartbeat
    "upsert_heartbeat",
    "get_heartbeat",
    # Player
    "upsert_player",
    "get_player_by_name",
    "get_or_add_player_by_name",
    "update_player_last_seen",
    "update_player_skin",
    # Player Online Status
    "upsert_player_online_status",
    "set_player_offline",
    "set_all_players_offline_on_server",
    "get_online_players_on_server",
    "get_online_players_grouped_by_server",
    # Player Session
    "create_session",
    "get_open_session",
    "end_session",
    "get_all_open_sessions_on_server",
    # Player Chat
    "create_chat_message",
    # Player Achievement
    "upsert_achievement",
]
