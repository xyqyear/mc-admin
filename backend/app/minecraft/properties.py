"""Minecraft server.properties parser and model."""

from typing import Optional

from pydantic import BaseModel, Field


class ServerProperties(BaseModel):
    """Minecraft server.properties configuration model.

    All fields are optional to support partial configurations.

    THIS FILE IS READ ONLY. Any modifications should be done with docker compose.
    """

    accepts_transfers: Optional[bool] = Field(None, alias="accepts-transfers")
    allow_flight: Optional[bool] = Field(None, alias="allow-flight")
    broadcast_console_to_ops: Optional[bool] = Field(None, alias="broadcast-console-to-ops")
    broadcast_rcon_to_ops: Optional[bool] = Field(None, alias="broadcast-rcon-to-ops")
    bug_report_link: Optional[str] = Field(None, alias="bug-report-link")
    difficulty: Optional[str] = None
    enable_code_of_conduct: Optional[bool] = Field(None, alias="enable-code-of-conduct")
    enable_jmx_monitoring: Optional[bool] = Field(None, alias="enable-jmx-monitoring")
    enable_query: Optional[bool] = Field(None, alias="enable-query")
    enable_rcon: Optional[bool] = Field(None, alias="enable-rcon")
    enable_status: Optional[bool] = Field(None, alias="enable-status")
    enforce_secure_profile: Optional[bool] = Field(None, alias="enforce-secure-profile")
    enforce_whitelist: Optional[bool] = Field(None, alias="enforce-whitelist")
    entity_broadcast_range_percentage: Optional[int] = Field(None, alias="entity-broadcast-range-percentage")
    force_gamemode: Optional[bool] = Field(None, alias="force-gamemode")
    function_permission_level: Optional[int] = Field(None, alias="function-permission-level")
    gamemode: Optional[str] = None
    generate_structures: Optional[bool] = Field(None, alias="generate-structures")
    generator_settings: Optional[str] = Field(None, alias="generator-settings")
    hardcore: Optional[bool] = None
    hide_online_players: Optional[bool] = Field(None, alias="hide-online-players")
    initial_disabled_packs: Optional[str] = Field(None, alias="initial-disabled-packs")
    initial_enabled_packs: Optional[str] = Field(None, alias="initial-enabled-packs")
    level_name: Optional[str] = Field(None, alias="level-name")
    level_seed: Optional[str] = Field(None, alias="level-seed")
    level_type: Optional[str] = Field(None, alias="level-type")
    log_ips: Optional[bool] = Field(None, alias="log-ips")
    management_server_enabled: Optional[bool] = Field(None, alias="management-server-enabled")
    management_server_host: Optional[str] = Field(None, alias="management-server-host")
    management_server_port: Optional[int] = Field(None, alias="management-server-port")
    management_server_secret: Optional[str] = Field(None, alias="management-server-secret")
    management_server_tls_enabled: Optional[bool] = Field(None, alias="management-server-tls-enabled")
    management_server_tls_keystore: Optional[str] = Field(None, alias="management-server-tls-keystore")
    management_server_tls_keystore_password: Optional[str] = Field(None, alias="management-server-tls-keystore-password")
    max_chained_neighbor_updates: Optional[int] = Field(None, alias="max-chained-neighbor-updates")
    max_players: Optional[int] = Field(None, alias="max-players")
    max_tick_time: Optional[int] = Field(None, alias="max-tick-time")
    max_world_size: Optional[int] = Field(None, alias="max-world-size")
    motd: Optional[str] = None
    network_compression_threshold: Optional[int] = Field(None, alias="network-compression-threshold")
    online_mode: Optional[bool] = Field(None, alias="online-mode")
    op_permission_level: Optional[int] = Field(None, alias="op-permission-level")
    pause_when_empty_seconds: Optional[int] = Field(None, alias="pause-when-empty-seconds")
    player_idle_timeout: Optional[int] = Field(None, alias="player-idle-timeout")
    prevent_proxy_connections: Optional[bool] = Field(None, alias="prevent-proxy-connections")
    query_port: Optional[int] = Field(None, alias="query.port")
    rate_limit: Optional[int] = Field(None, alias="rate-limit")
    rcon_password: Optional[str] = Field(None, alias="rcon.password")
    rcon_port: Optional[int] = Field(None, alias="rcon.port")
    region_file_compression: Optional[str] = Field(None, alias="region-file-compression")
    require_resource_pack: Optional[bool] = Field(None, alias="require-resource-pack")
    resource_pack: Optional[str] = Field(None, alias="resource-pack")
    resource_pack_id: Optional[str] = Field(None, alias="resource-pack-id")
    resource_pack_prompt: Optional[str] = Field(None, alias="resource-pack-prompt")
    resource_pack_sha1: Optional[str] = Field(None, alias="resource-pack-sha1")
    server_ip: Optional[str] = Field(None, alias="server-ip")
    server_port: Optional[int] = Field(None, alias="server-port")
    simulation_distance: Optional[int] = Field(None, alias="simulation-distance")
    spawn_protection: Optional[int] = Field(None, alias="spawn-protection")
    status_heartbeat_interval: Optional[int] = Field(None, alias="status-heartbeat-interval")
    sync_chunk_writes: Optional[bool] = Field(None, alias="sync-chunk-writes")
    text_filtering_config: Optional[str] = Field(None, alias="text-filtering-config")
    text_filtering_version: Optional[int] = Field(None, alias="text-filtering-version")
    use_native_transport: Optional[bool] = Field(None, alias="use-native-transport")
    view_distance: Optional[int] = Field(None, alias="view-distance")
    white_list: Optional[bool] = Field(None, alias="white-list")

    class Config:
        populate_by_name = True

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
