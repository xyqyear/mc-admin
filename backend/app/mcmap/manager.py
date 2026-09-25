"""Singleton registry of per-(server, region_path) render queues."""

import asyncio

from ..runtime_resources import current_runtime
from .cache import ServerMapCache
from .queue import ServerRenderQueue


class MCMapManager:
    def __init__(self) -> None:
        self._queues: dict[tuple[str, str], ServerRenderQueue] = {}

    def get_queue(
        self, server_name: str, region_path: str, cache: ServerMapCache
    ) -> ServerRenderQueue:
        key = (server_name, region_path)
        if key not in self._queues:
            self._queues[key] = ServerRenderQueue(
                server_name, region_path, cache
            )
        return self._queues[key]

    async def close(self) -> None:
        queues = list(self._queues.values())
        self._queues.clear()
        results = await asyncio.gather(*(queue.close() for queue in queues), return_exceptions=True)
        errors = [result for result in results if isinstance(result, Exception)]
        if errors:
            raise ExceptionGroup("地图队列关闭失败", errors)


def get_mcmap_manager() -> MCMapManager:
    return current_runtime().resource('mcmap_manager')
