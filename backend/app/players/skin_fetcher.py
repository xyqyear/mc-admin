"""Skin fetching from Mojang API."""

import asyncio
import base64
import io
import json
from typing import Optional, Tuple

import httpx
from PIL import Image

from ..dynamic_config import config
from ..logger import logger


class SkinFetcher:
    """Fetches player skins from Mojang API."""

    def __init__(self):
        """Initialize skin fetcher."""
        self.session_server_url = (
            "https://sessionserver.mojang.com/session/minecraft/profile/{uuid}"
        )

    async def fetch_player_skin(self, uuid: str) -> Optional[Tuple[bytes, bytes]]:
        """Fetch player skin and avatar from Mojang API.

        Args:
            uuid: Player UUID (without dashes)

        Returns:
            Tuple of (skin_data, avatar_data) as PNG bytes, or None if failed
        """
        try:
            # Add rate limiting delay
            await asyncio.sleep(config.players.skin_fetcher.rate_limit_delay_seconds)

            # Format UUID (ensure no dashes)
            uuid_clean = uuid.replace("-", "")

            request_timeout = config.players.skin_fetcher.request_timeout_seconds
            async with httpx.AsyncClient(timeout=request_timeout) as client:
                # Get player profile
                url = self.session_server_url.format(uuid=uuid_clean)
                response = await client.get(url)

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

                # Extract texture data
                textures_base64 = None
                for prop in profile_data.get("properties", []):
                    if prop.get("name") == "textures":
                        textures_base64 = prop.get("value")
                        break

                if not textures_base64:
                    logger.warning(f"No textures found for player {uuid_clean}")
                    return None

                # Decode texture data
                textures_json = base64.b64decode(textures_base64).decode("utf-8")
                textures = json.loads(textures_json)

                # Get skin URL
                skin_url = textures.get("textures", {}).get("SKIN", {}).get("url")
                if not skin_url:
                    logger.warning(f"No skin URL found for player {uuid_clean}")
                    return None

                # Download skin
                response = await client.get(skin_url)

                if response.status_code != 200:
                    logger.error(f"Failed to download skin: {response.status_code}")
                    return None

                skin_bytes = response.content

                # Extract avatar from skin
                avatar_bytes = self._extract_avatar(skin_bytes)

                if avatar_bytes is None:
                    logger.error(f"Failed to extract avatar for player {uuid_clean}")
                    return None

                return (skin_bytes, avatar_bytes)

        except httpx.TimeoutException:
            logger.error(f"Timeout fetching skin for {uuid}")
            return None
        except Exception as e:
            logger.error(f"Error fetching skin for {uuid}: {e}", exc_info=True)
            return None

    def _extract_avatar(self, skin_bytes: bytes) -> Optional[bytes]:
        """Extract player avatar from skin image.

        Args:
            skin_bytes: Full skin PNG bytes

        Returns:
            Avatar PNG bytes (16x16), or None if failed
        """
        try:
            # Load skin image
            skin_image = Image.open(io.BytesIO(skin_bytes))

            # Extract head region (8x8 to 16x16 on the skin texture)
            # The face is located at (8, 8) with size (8, 8)
            avatar = skin_image.crop((8, 8, 16, 16))

            # Convert to PNG bytes
            output = io.BytesIO()
            avatar.save(output, format="PNG")
            return output.getvalue()

        except Exception as e:
            logger.error(f"Error extracting avatar: {e}", exc_info=True)
            return None
