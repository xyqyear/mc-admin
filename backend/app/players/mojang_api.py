"""Mojang API utilities for player information."""

from typing import Optional

import aiohttp

from ..logger import logger


async def fetch_player_uuid_from_mojang(player_name: str) -> Optional[str]:
    """Fetch player UUID from Mojang API.

    Args:
        player_name: Player username

    Returns:
        UUID (without dashes) or None if not found
    """
    try:
        url = f"https://api.mojang.com/users/profiles/minecraft/{player_name}"
        async with aiohttp.ClientSession() as client_session:
            async with client_session.get(
                url, timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                if response.status == 404:
                    logger.warning(f"Player not found in Mojang API: {player_name}")
                    return None
                elif response.status == 429:
                    logger.warning(f"Mojang API rate limited for player: {player_name}")
                    return None
                elif response.status == 200:
                    data = await response.json()
                    return data.get("id")  # UUID without dashes
                else:
                    logger.error(
                        f"Unexpected Mojang API response {response.status} for player: {player_name}"
                    )
                    return None
    except Exception as e:
        logger.error(
            f"Error fetching UUID from Mojang API for {player_name}: {e}",
            exc_info=True,
        )
        return None
