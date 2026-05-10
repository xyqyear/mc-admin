"""Skin fetching from Mojang API."""

import asyncio
import base64
import json
from typing import Optional, Tuple

import httpx

from ..dynamic_config import config
from ..logger import log_exception, logger
from ..utils import async_fs


class SkinFetcher:
    def __init__(self):
        self.session_server_url = (
            "https://sessionserver.mojang.com/session/minecraft/profile/{uuid}"
        )

    @log_exception("Error fetching player skin for {uuid}: ")
    async def fetch_player_skin(self, uuid: str) -> Optional[Tuple[bytes, bytes]]:
        """Return ``(skin_png, avatar_png)`` for ``uuid``, or ``None`` on failure."""
        await asyncio.sleep(config.players.skin_fetcher.rate_limit_delay_seconds)

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

            textures_base64 = None
            for prop in profile_data.get("properties", []):
                if prop.get("name") == "textures":
                    textures_base64 = prop.get("value")
                    break

            if not textures_base64:
                logger.warning(f"No textures found for player {uuid_clean}")
                return None

            textures_json = base64.b64decode(textures_base64).decode("utf-8")
            textures = json.loads(textures_json)

            skin_url = textures.get("textures", {}).get("SKIN", {}).get("url")
            if not skin_url:
                logger.warning(f"No skin URL found for player {uuid_clean}")
                return None

            response = await client.get(skin_url)

            if response.status_code != 200:
                logger.error(f"Failed to download skin: {response.status_code}")
                return None

            skin_bytes = response.content

            # PIL is CPU-bound — keep the avatar extraction off the event loop.
            try:
                avatar_bytes = await async_fs.extract_skin_avatar(skin_bytes)
            except Exception as e:
                logger.error(
                    f"Failed to extract avatar for player {uuid_clean}: {e}"
                )
                return None

            return (skin_bytes, avatar_bytes)


skin_fetcher = SkinFetcher()
