"""Singleton registry of per-(server, region_path) render queues."""

from typing import Dict, Tuple

from .cache import ServerMapCache
from .queue import ServerRenderQueue


class MCMapManager:
    def __init__(self) -> None:
        self._queues: Dict[Tuple[str, str], ServerRenderQueue] = {}

    def get_queue(
        self, server_name: str, region_path: str, cache: ServerMapCache
    ) -> ServerRenderQueue:
        key = (server_name, region_path)
        if key not in self._queues:
            self._queues[key] = ServerRenderQueue(
                server_name, region_path, cache
            )
        return self._queues[key]


mcmap_manager = MCMapManager()
