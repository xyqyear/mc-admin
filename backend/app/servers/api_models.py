from typing import Literal

from pydantic import BaseModel, Field

from app.servers.restart_schedule import RestartScheduleRequest

MinecraftColor = Literal[
    "black",
    "dark_blue",
    "dark_green",
    "dark_aqua",
    "dark_red",
    "dark_purple",
    "gold",
    "gray",
    "dark_gray",
    "blue",
    "green",
    "aqua",
    "red",
    "light_purple",
    "yellow",
    "white",
]


class CreateServerRequest(BaseModel):
    """Request model for server creation.

    Supports two modes:
    - Traditional mode: Provide yaml_content directly
    - Template mode: Provide template_id and variable_values

    Optionally bundles a restart schedule, eliminating the need for a
    follow-up POST /restart-schedule round-trip.
    """

    yaml_content: str | None = None
    template_id: int | None = None
    variable_values: dict | None = None
    restart_schedule: RestartScheduleRequest | None = None


class ServerInfo(BaseModel):
    id: str
    server_generation: int | None = None
    name: str
    serverType: str
    gameVersion: str
    gamePort: int
    maxMemoryBytes: int
    rconPort: int
    javaVersion: int


class ServerMaintenance(BaseModel):
    active: bool = False
    kind: str | None = None
    description: str | None = None
    task_id: str | None = None


class SyncRequest(BaseModel):
    dry_run: bool = False
    # Bypass the empty-filesystem safety guard (used when a mount has failed).
    force: bool = False


class RconCommandRequest(BaseModel):
    command: str = Field(min_length=1, max_length=1000)


class RconCommandResponse(BaseModel):
    output: str


class ServerMessageRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    target_player: str | None = Field(default=None, pattern=r"^\w{1,16}$")
    color: MinecraftColor = "yellow"


class ServerOperation(BaseModel):
    action: str


class ServerListItem(BaseModel):
    """Server list item model with basic server information only"""

    id: str
    name: str
    serverType: str
    gameVersion: str
    gamePort: int
    maxMemoryBytes: int
    rconPort: int
    javaVersion: int
