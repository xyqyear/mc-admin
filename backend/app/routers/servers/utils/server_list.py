from pydantic import BaseModel

from ....minecraft import MCInstance


class ServerListItem(BaseModel):
    """Server list item model with basic server information only"""
    id: str
    name: str
    serverType: str
    gameVersion: str
    gamePort: int
    maxMemoryBytes: int
    rconPort: int


async def get_server_list_item(instance: MCInstance) -> ServerListItem:
    """Helper to get basic server info for a single instance"""
    try:
        server_id = instance.get_name()

        # Get only basic server info
        server_info = await instance.get_server_info()

        return ServerListItem(
            id=server_id,
            name=server_info.name,
            serverType=server_info.server_type or "vanilla",
            gameVersion=server_info.game_version or "latest",
            gamePort=server_info.game_port or 25565,
            maxMemoryBytes=server_info.max_memory_bytes or 2147483648,
            rconPort=server_info.rcon_port or 25575,
        )

    except Exception as e:
        # Log error but don't fail the entire request
        print(f"Error getting server list item for {instance.get_name()}: {e}")
        # Return minimal data
        return ServerListItem(
            id=instance.get_name(),
            name=instance.get_name(),
            serverType="unknown",
            gameVersion="unknown",
            gamePort=25565,
            maxMemoryBytes=2147483648,
            rconPort=25575,
        )