"""Port conflict checking utilities for server management."""

from typing import Optional

import psutil
import yaml

from ..logger import logger
from ..minecraft import docker_mc_manager
from ..minecraft.compose import MCComposeFile
from ..minecraft.docker.compose_file import ComposeFile


def extract_ports_from_yaml(yaml_content: str) -> tuple[int, int]:
    """Extract game port and RCON port from YAML content.

    Args:
        yaml_content: Docker Compose YAML content

    Returns:
        tuple[int, int]: (game_port, rcon_port)

    Raises:
        ValueError: If YAML is invalid or doesn't contain required ports
    """
    compose_dict = yaml.safe_load(yaml_content)
    compose_file = ComposeFile.from_dict(compose_dict)
    mc_compose = MCComposeFile(compose_file)
    return mc_compose.get_game_port(), mc_compose.get_rcon_port()


def get_system_used_ports() -> set[int]:
    """Get the set of ports currently in use by the system.

    Returns:
        Set of port numbers that are currently bound (LISTEN or ESTABLISHED).
    """
    used_ports: set[int] = set()
    for conn in psutil.net_connections(kind="inet"):
        if conn.laddr:
            used_ports.add(conn.laddr.port)
    return used_ports


async def get_server_used_ports() -> dict[int, str]:
    """Get ports used by Minecraft servers.

    Returns:
        Dict mapping port number to server name.
    """
    port_map: dict[int, str] = {}
    instances = await docker_mc_manager.get_all_instances()

    for instance in instances:
        compose_file_path = await instance.get_compose_file_path()
        if compose_file_path is None:
            continue

        try:
            compose_content = await instance.get_compose_file()
            game_port, rcon_port = extract_ports_from_yaml(compose_content)
            port_map[game_port] = instance.get_name()
            port_map[rcon_port] = instance.get_name()
        except Exception:
            logger.warning(
                f"Failed to parse compose file for {instance.get_name()} "
                "while checking port conflicts"
            )
            continue

    return port_map


async def check_port_conflicts(
    game_port: int,
    rcon_port: int,
    exclude_server_id: Optional[str] = None,
) -> list[str]:
    """Check for port conflicts with existing servers and system ports.

    Args:
        game_port: Game port to check
        rcon_port: RCON port to check
        exclude_server_id: Server ID to exclude from checking (for rebuild scenarios)

    Returns:
        List of conflict messages, empty if no conflicts
    """
    conflicts = []
    ports_to_check = {game_port, rcon_port}

    # Collect ports from all servers (with server name mapping)
    server_port_map = await get_server_used_ports()

    # Collect system ports
    system_ports = get_system_used_ports()

    # System ports that are NOT from known servers
    server_port_set = set(server_port_map.keys())
    non_server_system_ports = system_ports - server_port_set

    # Check against other servers
    for port in ports_to_check:
        if port in server_port_map:
            owner = server_port_map[port]
            if exclude_server_id and owner == exclude_server_id:
                continue
            port_label = "Game port" if port == game_port else "RCON port"
            conflicts.append(f"{port_label} {port} is already used by server '{owner}'")

    # Check against system ports (non-server)
    if game_port in non_server_system_ports:
        conflicts.append(f"Game port {game_port} is already in use by the system")
    if rcon_port in non_server_system_ports:
        conflicts.append(f"RCON port {rcon_port} is already in use by the system")

    return conflicts
