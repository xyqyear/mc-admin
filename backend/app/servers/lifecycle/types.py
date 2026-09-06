
from pydantic import BaseModel

from ...routers.servers.restart_schedule import RestartScheduleRequest


class CreateServerSpec(BaseModel):
    # Either yaml_content OR (template_id + variable_values) must be set.
    yaml_content: str | None = None
    template_id: int | None = None
    variable_values: dict | None = None
    restart_schedule: RestartScheduleRequest | None = None


class CreateServerResult(BaseModel):
    server_id: str
    game_port: int
    rcon_port: int
    restart_cronjob_id: str | None = None


class RemoveServerResult(BaseModel):
    server_id: str
    cancelled_restart_cronjob_ids: list[str] = []
    cancelled_background_task_ids: list[str] = []
    closed_sessions: int = 0


class SyncEntryError(BaseModel):
    server_id: str
    stage: str  # validate | adopt | deactivate
    error: str


class SyncDryRunEntry(BaseModel):
    server_id: str
    action: str  # adopt | deactivate
    game_port: int | None = None
    rcon_port: int | None = None
    restart_cronjob_count: int | None = None
    open_session_count: int | None = None


class SyncResult(BaseModel):
    applied: bool
    adopted: list[CreateServerResult] = []
    removed: list[RemoveServerResult] = []
    preview: list[SyncDryRunEntry] = []
    errors: list[SyncEntryError] = []
