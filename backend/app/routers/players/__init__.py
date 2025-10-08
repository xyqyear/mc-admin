"""Player management routers."""

from .achievements import router as achievements_router
from .chat import router as chat_router
from .players import router as players_router
from .sessions import router as sessions_router
from .statistics import router as statistics_router

__all__ = [
    "players_router",
    "sessions_router",
    "chat_router",
    "achievements_router",
    "statistics_router",
]
