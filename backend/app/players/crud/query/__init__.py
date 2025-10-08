"""Query functions for player management API."""

from .achievement_query import (
    get_player_achievements,
    get_server_achievement_leaderboard,
)
from .chat_query import get_player_chat_messages, get_server_chat_messages
from .player_query import (
    get_all_players_summary,
    get_player_detail_by_name,
    get_player_detail_by_uuid,
)
from .session_query import (
    get_player_session_stats,
    get_player_sessions,
    get_server_online_players,
)
from .statistics_query import (
    get_activity_trend,
    get_global_player_stats,
    get_server_player_stats,
)

__all__ = [
    # Player queries
    "get_all_players_summary",
    "get_player_detail_by_uuid",
    "get_player_detail_by_name",
    # Session queries
    "get_player_sessions",
    "get_server_online_players",
    "get_player_session_stats",
    # Chat queries
    "get_player_chat_messages",
    "get_server_chat_messages",
    # Achievement queries
    "get_player_achievements",
    "get_server_achievement_leaderboard",
    # Statistics queries
    "get_global_player_stats",
    "get_activity_trend",
    "get_server_player_stats",
]
