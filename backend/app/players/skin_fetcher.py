"""Skin fetching from Mojang API."""

import base64
import json
from dataclasses import dataclass
from typing import Optional, Tuple

import httpx

from ..dynamic_config import config
from ..logger import log_exception, logger
from ..utils import async_fs


@dataclass(frozen=True)
class PlayerProfileFetchResult:
    name: str
    skin_data: Optional[bytes]
    avatar_data: Optional[bytes]


class SkinFetcher:
    def __init__(self):
        self.session_server_url = (
            "https://sessionserver.mojang.com/session/minecraft/profile/{uuid}"
        )

    @log_exception("Error fetching player profile for {uuid}: ")
    async def fetch_player_profile(
        self, uuid: str
    ) -> Optional[PlayerProfileFetchResult]:
        """Return Mojang profile data for ``uuid``, or ``None`` on failure."""
        uuid_clean = uuid.replace("-", "")

        request_timeout = config.players.skin_fetcher.request_timeout_seconds
        async with httpx.AsyncClient(timeout=request_timeout) as client:
            url = self.session_server_url.format(uuid=uuid_clean)
            try:
                response = await client.get(url)
            except httpx.TimeoutException:
                logger.error(f"Timeout fetching profile for {uuid_clean}")
                return None

            if response.status_code == 404:
                logger.warning(f"Player not found: {uuid_clean}")
                return None
            elif response.status_code == 429:
                logger.warning("Rate limited by Mojang API")
                return None
            elif response.status_code != 200:
                logger.error(f"Mojang API error: {response.status_code}")
                return None

            profile_data = response.json()
            name = profile_data.get("name")
            if not isinstance(name, str) or not name.strip():
                logger.warning(f"No player name found for {uuid_clean}")
                return None

            textures_base64 = None
            for prop in profile_data.get("properties", []):
                if prop.get("name") == "textures":
                    textures_base64 = prop.get("value")
                    break

            if not textures_base64:
                logger.warning(f"No textures found for player {uuid_clean}")
                return PlayerProfileFetchResult(
                    name=name,
                    skin_data=None,
                    avatar_data=None,
                )

            textures_json = base64.b64decode(textures_base64).decode("utf-8")
            textures = json.loads(textures_json)

            skin_url = textures.get("textures", {}).get("SKIN", {}).get("url")
            if not skin_url:
                logger.warning(f"No skin URL found for player {uuid_clean}")
                return PlayerProfileFetchResult(
                    name=name,
                    skin_data=None,
                    avatar_data=None,
                )

            response = await client.get(skin_url)

            if response.status_code != 200:
                logger.error(f"Failed to download skin: {response.status_code}")
                return PlayerProfileFetchResult(
                    name=name,
                    skin_data=None,
                    avatar_data=None,
                )

            skin_bytes = response.content

            # PIL is CPU-bound; keep the avatar extraction off the event loop.
            try:
                avatar_bytes = await async_fs.extract_skin_avatar(skin_bytes)
            except Exception as e:
                logger.error(
                    f"Failed to extract avatar for player {uuid_clean}: {e}"
                )
                return PlayerProfileFetchResult(
                    name=name,
                    skin_data=skin_bytes,
                    avatar_data=None,
                )

            return PlayerProfileFetchResult(
                name=name,
                skin_data=skin_bytes,
                avatar_data=avatar_bytes,
            )

    @log_exception("Error fetching player skin for {uuid}: ")
    async def fetch_player_skin(self, uuid: str) -> Optional[Tuple[bytes, bytes]]:
        """Return ``(skin_png, avatar_png)`` for ``uuid``, or ``None`` on failure."""
        result = await self.fetch_player_profile(uuid)
        if not result or not result.skin_data or not result.avatar_data:
            return None
        return (result.skin_data, result.avatar_data)


skin_fetcher = SkinFetcher()
