"""Pydantic types for server lifecycle orchestrators and sync endpoint."""

from typing import Optional

from pydantic import BaseModel

from ...routers.servers.restart_schedule import RestartScheduleRequest


class CreateServerSpec(BaseModel):
    """Specification for creating a server.

    Either yaml_content OR (template_id + variable_values) must be provided.
    Optionally bundles a restart schedule that is created in the same round-trip.
    """

    yaml_content: Optional[str] = None
    template_id: Optional[int] = None
    variable_values: Optional[dict] = None
    restart_schedule: Optional[RestartScheduleRequest] = None


class CreateServerResult(BaseModel):
    """Outcome of a successful create_server_full call."""

    server_id: str
    game_port: int
    rcon_port: int
    restart_cronjob_id: Optional[str] = None


class RemoveServerResult(BaseModel):
    """Outcome of a successful remove_server_full or deactivate_server_partial call."""

    server_id: str
    cancelled_restart_cronjob_ids: list[str] = []
    cancelled_background_task_ids: list[str] = []
    closed_sessions: int = 0


class SyncEntryError(BaseModel):
    """Per-server error reported by the sync endpoint."""

    server_id: str
    stage: str  # "validate" | "adopt" | "deactivate"
    error: str


class SyncDryRunEntry(BaseModel):
    """Preview of a single change in the sync dry-run payload.

    For adopt entries, game_port/rcon_port are populated.
    For deactivate entries, restart_cronjob_count/open_session_count are populated.
    """

    server_id: str
    action: str  # "adopt" | "deactivate"
    game_port: Optional[int] = None
    rcon_port: Optional[int] = None
    restart_cronjob_count: Optional[int] = None
    open_session_count: Optional[int] = None


class SyncResult(BaseModel):
    """Combined result of POST /api/servers/sync (both dry-run and apply)."""

    applied: bool
    adopted: list[CreateServerResult] = []
    removed: list[RemoveServerResult] = []
    preview: list[SyncDryRunEntry] = []
    errors: list[SyncEntryError] = []
