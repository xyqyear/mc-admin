from typing import Optional

from pydantic import BaseModel

from ...routers.servers.restart_schedule import RestartScheduleRequest


class CreateServerSpec(BaseModel):
    # Either yaml_content OR (template_id + variable_values) must be set.
    yaml_content: Optional[str] = None
    template_id: Optional[int] = None
    variable_values: Optional[dict] = None
    restart_schedule: Optional[RestartScheduleRequest] = None


class CreateServerResult(BaseModel):
    server_id: str
    game_port: int
    rcon_port: int
    restart_cronjob_id: Optional[str] = None


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
    game_port: Optional[int] = None
    rcon_port: Optional[int] = None
    restart_cronjob_count: Optional[int] = None
    open_session_count: Optional[int] = None


class SyncResult(BaseModel):
    applied: bool
    adopted: list[CreateServerResult] = []
    removed: list[RemoveServerResult] = []
    preview: list[SyncDryRunEntry] = []
    errors: list[SyncEntryError] = []
