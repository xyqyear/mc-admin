"""Mojang API utilities for player information."""

from typing import Optional

import httpx

from ..logger import log_exception, logger


@log_exception("Error fetching player UUID from Mojang API for {player_name}: ")
async def fetch_player_uuid_from_mojang(player_name: str) -> Optional[str]:
    """Return the dashless UUID for ``player_name``, or ``None`` if not found."""
    url = f"https://api.mojang.com/users/profiles/minecraft/{player_name}"
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(url)

        if response.status_code == 404:
            logger.warning(f"Player not found in Mojang API: {player_name}")
            return None
        elif response.status_code == 429:
            logger.warning(f"Mojang API rate limited for player: {player_name}")
            return None
        elif response.status_code == 200:
            data = response.json()
            return data.get("id")
        else:
            logger.error(
                f"Unexpected Mojang API response {response.status_code} for player: {player_name}"
            )
