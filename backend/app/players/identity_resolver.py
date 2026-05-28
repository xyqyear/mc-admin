"""Player identity resolution from usercache.json with Mojang fallback."""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from uuid import UUID

import aiofiles
from aiofiles import os as aioos
from pydantic import BaseModel, ConfigDict, ValidationError

from ..logger import logger
from ..minecraft import docker_mc_manager
from . import mojang_api


class UserCacheEntry(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: Optional[str] = None
    uuid: Optional[str] = None


@dataclass(frozen=True)
class PlayerIdentity:
    uuid: str
    name: str


@dataclass(frozen=True)
class UserCacheLookup:
    identity: Optional[PlayerIdentity]
    blocked_by_invalid_uuid: bool = False


@dataclass(frozen=True)
class UserCacheData:
    by_name: dict[str, PlayerIdentity]
    by_uuid: dict[str, PlayerIdentity]
    invalid_names: set[str]
    invalid_uuids: set[str]


def normalize_uuid(value: str) -> Optional[str]:
    """Return dashless lowercase UUID text, or None for invalid UUID syntax."""
    uuid_text = value.replace("-", "").lower()
    if len(uuid_text) != 32 or any(c not in "0123456789abcdef" for c in uuid_text):
        return None
    try:
        return UUID(uuid_text).hex
    except ValueError:
        return None


def is_online_uuid(value: str) -> bool:
    """Minecraft online UUIDs are version 4 UUIDs."""
    normalized = normalize_uuid(value)
    if normalized is None:
        return False
    return UUID(normalized).version == 4


def normalize_online_uuid(value: str) -> Optional[str]:
    """Return normalized UUID only when it is an online-mode UUID."""
    normalized = normalize_uuid(value)
    if normalized is None:
        return None
    if UUID(normalized).version != 4:
        return None
    return normalized


def _usercache_path(server_id: str) -> Path:
    return docker_mc_manager.get_instance(server_id).get_data_path() / "usercache.json"


async def _load_usercache(path: Path) -> UserCacheData:
    by_name: dict[str, PlayerIdentity] = {}
    by_uuid: dict[str, PlayerIdentity] = {}
    invalid_names: set[str] = set()
    invalid_uuids: set[str] = set()

    if not await aioos.path.exists(path):
        return UserCacheData(by_name, by_uuid, invalid_names, invalid_uuids)

    try:
        async with aiofiles.open(path, "r", encoding="utf-8") as f:
            raw = await f.read()
        parsed = json.loads(raw)
    except Exception as e:
        logger.warning(f"Failed to read usercache.json at {path}: {e}")
        return UserCacheData(by_name, by_uuid, invalid_names, invalid_uuids)

    if not isinstance(parsed, list):
        return UserCacheData(by_name, by_uuid, invalid_names, invalid_uuids)

    for entry in parsed:
        try:
            cache_entry = UserCacheEntry.model_validate(entry)
        except ValidationError:
            continue

        name = cache_entry.name
        uuid_value = cache_entry.uuid
        if not name:
            continue
        if not uuid_value:
            continue

        name_key = name.lower()
        normalized = normalize_uuid(uuid_value)
        if normalized is None or not is_online_uuid(normalized):
            invalid_names.add(name_key)
            if normalized is not None:
                invalid_uuids.add(normalized)
            continue

        identity = PlayerIdentity(uuid=normalized, name=name)
        by_name.setdefault(name_key, identity)
        by_uuid.setdefault(normalized, identity)

    return UserCacheData(by_name, by_uuid, invalid_names, invalid_uuids)


async def lookup_usercache_by_name(server_id: str, player_name: str) -> UserCacheLookup:
    cache = await _load_usercache(_usercache_path(server_id))
    name_key = player_name.lower()
    identity = cache.by_name.get(name_key)
    if identity is not None:
        return UserCacheLookup(identity=identity)
    return UserCacheLookup(
        identity=None,
        blocked_by_invalid_uuid=name_key in cache.invalid_names,
    )


async def lookup_usercache_by_uuid(server_id: str, uuid: str) -> UserCacheLookup:
    normalized = normalize_uuid(uuid)
    if normalized is None:
        return UserCacheLookup(identity=None, blocked_by_invalid_uuid=True)
    if not is_online_uuid(normalized):
        return UserCacheLookup(identity=None, blocked_by_invalid_uuid=True)

    cache = await _load_usercache(_usercache_path(server_id))
    identity = cache.by_uuid.get(normalized)
    if identity is not None:
        return UserCacheLookup(identity=identity)
    return UserCacheLookup(
        identity=None,
        blocked_by_invalid_uuid=normalized in cache.invalid_uuids,
    )


async def resolve_player_by_name(
    server_id: str,
    player_name: str,
) -> Optional[PlayerIdentity]:
    """Resolve a player name to an online UUID, preferring usercache.json."""
    cached = await lookup_usercache_by_name(server_id, player_name)
    if cached.identity is not None:
        return cached.identity
    if cached.blocked_by_invalid_uuid:
        logger.warning(
            f"Refusing Mojang fallback for {player_name}: usercache.json has a non-v4 UUID"
        )
        return None

    uuid = await mojang_api.fetch_player_uuid_from_mojang(player_name)
    if uuid is None:
        return None
    normalized = normalize_online_uuid(uuid)
    if normalized is None:
        logger.warning(f"Mojang returned non-v4 UUID for player {player_name}: {uuid}")
        return None
    return PlayerIdentity(uuid=normalized, name=player_name)


async def resolve_player_by_uuid(
    server_id: str,
    uuid: str,
) -> Optional[PlayerIdentity]:
    """Resolve an online UUID to a player name, preferring usercache.json."""
    normalized = normalize_online_uuid(uuid)
    if normalized is None:
        return None

    cached = await lookup_usercache_by_uuid(server_id, normalized)
    if cached.identity is not None:
        return cached.identity
    if cached.blocked_by_invalid_uuid:
        logger.warning(
            f"Refusing Mojang fallback for {uuid}: usercache.json has a non-v4 UUID"
        )
        return None

    name = await mojang_api.fetch_player_name_from_mojang(normalized)
    if name is None:
        return None
    return PlayerIdentity(uuid=normalized, name=name)
