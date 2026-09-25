"""Public server read models assembled from Minecraft configuration."""

from ..minecraft import MCInstance
from .api_models import ServerListItem


async def get_server_list_item(instance: MCInstance) -> ServerListItem:
    """Helper to get basic server info for a single instance"""
    server_id = instance.get_name()

    # Get only basic server info
    server_info = await instance.get_server_info()

    return ServerListItem(
        id=server_id,
        name=server_info.name,
        serverType=server_info.server_type,
        gameVersion=server_info.game_version,
        gamePort=server_info.game_port,
        maxMemoryBytes=server_info.max_memory_bytes,
        rconPort=server_info.rcon_port,
        javaVersion=server_info.java_version,
    )
