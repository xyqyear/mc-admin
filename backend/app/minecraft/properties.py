"""Minecraft server.properties parser and model."""

import asyncio
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator

DEFAULT_LEVEL_NAME = "world"


class ServerProperties(BaseModel):
    """Minecraft server.properties configuration model.

    All fields are optional to support partial configurations.

    THIS FILE IS READ ONLY. Any modifications should be done with docker compose.
    """

    accepts_transfers: bool | None = Field(None, alias="accepts-transfers")
    allow_flight: bool | None = Field(None, alias="allow-flight")
    broadcast_console_to_ops: bool | None = Field(None, alias="broadcast-console-to-ops")
    broadcast_rcon_to_ops: bool | None = Field(None, alias="broadcast-rcon-to-ops")
    bug_report_link: str | None = Field(None, alias="bug-report-link")
    difficulty: str | None = None
    enable_code_of_conduct: bool | None = Field(None, alias="enable-code-of-conduct")
    enable_jmx_monitoring: bool | None = Field(None, alias="enable-jmx-monitoring")
    enable_query: bool | None = Field(None, alias="enable-query")
    enable_rcon: bool | None = Field(None, alias="enable-rcon")
    enable_status: bool | None = Field(None, alias="enable-status")
    enforce_secure_profile: bool | None = Field(None, alias="enforce-secure-profile")
    enforce_whitelist: bool | None = Field(None, alias="enforce-whitelist")
    entity_broadcast_range_percentage: int | None = Field(None, alias="entity-broadcast-range-percentage")
    force_gamemode: bool | None = Field(None, alias="force-gamemode")
    function_permission_level: int | None = Field(None, alias="function-permission-level")
    gamemode: str | None = None
    generate_structures: bool | None = Field(None, alias="generate-structures")
    generator_settings: str | None = Field(None, alias="generator-settings")
    hardcore: bool | None = None
    hide_online_players: bool | None = Field(None, alias="hide-online-players")
    initial_disabled_packs: str | None = Field(None, alias="initial-disabled-packs")
    initial_enabled_packs: str | None = Field(None, alias="initial-enabled-packs")
    level_name: str | None = Field(None, alias="level-name")
    level_seed: int | str | None = Field(None, alias="level-seed")
    level_type: str | None = Field(None, alias="level-type")
    log_ips: bool | None = Field(None, alias="log-ips")
    management_server_enabled: bool | None = Field(None, alias="management-server-enabled")
    management_server_host: str | None = Field(None, alias="management-server-host")
    management_server_port: int | None = Field(None, alias="management-server-port")
    management_server_secret: str | None = Field(None, alias="management-server-secret")
    management_server_tls_enabled: bool | None = Field(None, alias="management-server-tls-enabled")
    management_server_tls_keystore: str | None = Field(None, alias="management-server-tls-keystore")
    management_server_tls_keystore_password: str | None = Field(None, alias="management-server-tls-keystore-password")
    max_chained_neighbor_updates: int | None = Field(None, alias="max-chained-neighbor-updates")
    max_players: int | None = Field(None, alias="max-players")
    max_tick_time: int | None = Field(None, alias="max-tick-time")
    max_world_size: int | None = Field(None, alias="max-world-size")
    motd: str | None = None
    network_compression_threshold: int | None = Field(None, alias="network-compression-threshold")
    online_mode: bool | None = Field(None, alias="online-mode")
    op_permission_level: int | None = Field(None, alias="op-permission-level")
    pause_when_empty_seconds: int | None = Field(None, alias="pause-when-empty-seconds")
    player_idle_timeout: int | None = Field(None, alias="player-idle-timeout")
    prevent_proxy_connections: bool | None = Field(None, alias="prevent-proxy-connections")
    query_port: int | None = Field(None, alias="query.port")
    rate_limit: int | None = Field(None, alias="rate-limit")
    rcon_password: str | None = Field(None, alias="rcon.password")
    rcon_port: int | None = Field(None, alias="rcon.port")
    region_file_compression: str | None = Field(None, alias="region-file-compression")
    require_resource_pack: bool | None = Field(None, alias="require-resource-pack")
    resource_pack: str | None = Field(None, alias="resource-pack")
    resource_pack_id: str | None = Field(None, alias="resource-pack-id")
    resource_pack_prompt: str | None = Field(None, alias="resource-pack-prompt")
    resource_pack_sha1: str | None = Field(None, alias="resource-pack-sha1")
    server_ip: str | None = Field(None, alias="server-ip")
    server_port: int | None = Field(None, alias="server-port")
    simulation_distance: int | None = Field(None, alias="simulation-distance")
    spawn_protection: int | None = Field(None, alias="spawn-protection")
    status_heartbeat_interval: int | None = Field(None, alias="status-heartbeat-interval")
    sync_chunk_writes: bool | None = Field(None, alias="sync-chunk-writes")
    text_filtering_config: str | None = Field(None, alias="text-filtering-config")
    text_filtering_version: int | None = Field(None, alias="text-filtering-version")
    use_native_transport: bool | None = Field(None, alias="use-native-transport")
    view_distance: int | None = Field(None, alias="view-distance")
    white_list: bool | None = Field(None, alias="white-list")

    @field_validator("difficulty", mode="before")
    @classmethod
    def convert_difficulty(cls, v):
        if isinstance(v, int):
            mapping = {0: "peaceful", 1: "easy", 2: "normal", 3: "hard"}
            return mapping.get(v, str(v))
        return v

    @field_validator("gamemode", mode="before")
    @classmethod
    def convert_gamemode(cls, v):
        if isinstance(v, int):
            mapping = {0: "survival", 1: "creative", 2: "adventure", 3: "spectator"}
            return mapping.get(v, str(v))
        return v

    model_config = ConfigDict(populate_by_name=True)

    @classmethod
    def from_server_properties(cls, content: str) -> "ServerProperties":
        """Parse server.properties file content into ServerProperties model.

        Args:
            content: Raw server.properties file content

        Returns:
            ServerProperties instance with parsed values
        """
        data = {}

        for line in content.strip().split('\n'):
            line = line.strip()

            # Skip empty lines and comments
            if not line or line.startswith('#'):
                continue

            # Split by first '=' only
            if '=' not in line:
                continue

            key, value = line.split('=', 1)
            key = key.strip()
            value = value.strip()

            # Skip empty values
            if not value:
                continue

            # Convert boolean strings
            if value.lower() == 'true':
                data[key] = True
            elif value.lower() == 'false':
                data[key] = False
            # Try to convert to int
            elif value.isdigit() or (value.startswith('-') and value[1:].isdigit()):
                data[key] = int(value)
            else:
                # Keep as string
                data[key] = value

        return cls(**data)


def read_level_name_sync(data_path: Path) -> str:
    """Level name from ``<data_path>/server.properties``; defaults to ``world``."""
    properties_path = data_path / "server.properties"
    try:
        content = properties_path.read_text()
    except OSError:
        return DEFAULT_LEVEL_NAME
    level_name = DEFAULT_LEVEL_NAME
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip() == "level-name" and value.strip():
            level_name = value.strip()
    return level_name


async def read_level_name(data_path: Path) -> str:
    return await asyncio.to_thread(read_level_name_sync, data_path)
