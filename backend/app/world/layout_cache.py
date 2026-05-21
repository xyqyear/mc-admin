import asyncio
import time
from dataclasses import dataclass
from pathlib import Path

from .layout import WorldRoot, discover_world_roots

LAYOUT_CACHE_TTL_SECONDS = 5.0


@dataclass
class _CacheEntry:
    value: list[WorldRoot] | None
    expires_at: float
    task: asyncio.Task[list[WorldRoot]] | None


_cache: dict[Path, _CacheEntry] = {}
_lock = asyncio.Lock()


async def get_cached_world_roots(data_path: Path) -> list[WorldRoot]:
    key = data_path.absolute()
    now = time.monotonic()

    async with _lock:
        entry = _cache.get(key)
        if entry is not None:
            if entry.value is not None and entry.expires_at > now:
                return entry.value
            if entry.task is not None and not entry.task.done():
                task = entry.task
            else:
                task = asyncio.create_task(discover_world_roots(data_path))
                _cache[key] = _CacheEntry(None, 0.0, task)
        else:
            task = asyncio.create_task(discover_world_roots(data_path))
            _cache[key] = _CacheEntry(None, 0.0, task)

    try:
        value = await task
    except Exception:
        async with _lock:
            entry = _cache.get(key)
            if entry is not None and entry.task is task:
                _cache.pop(key, None)
        raise

    async with _lock:
        entry = _cache.get(key)
        if entry is not None and entry.task is task:
            entry.value = value
            entry.expires_at = time.monotonic() + LAYOUT_CACHE_TTL_SECONDS
            entry.task = None
    return value


async def invalidate_world_layout(data_path: Path) -> None:
    async with _lock:
        _cache.pop(data_path.absolute(), None)


async def clear_world_layout_cache() -> None:
    async with _lock:
        _cache.clear()
