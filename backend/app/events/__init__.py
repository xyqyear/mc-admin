"""
Event system for MC Admin.

Provides a centralized event dispatcher for asynchronous event handling
across all application modules.
"""

from .base import BaseEvent
from .dispatcher import EventDispatcher, event_dispatcher
from .types import EventType

__all__ = [
    "BaseEvent",
    "EventDispatcher",
    "event_dispatcher",
    "EventType",
]
