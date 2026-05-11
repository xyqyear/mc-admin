"""Server creation API router supporting both traditional YAML and template modes."""

from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.database import get_db
from ...dependencies import get_current_user
from ...models import UserPublic
from ...servers.lifecycle import (
    CreateServerResult,
    CreateServerSpec,
    create_server_full,
)
from .restart_schedule import RestartScheduleRequest

router = APIRouter(
    prefix="/servers",
    tags=["server-creation"],
)


class CreateServerRequest(BaseModel):
    """Request model for server creation.

    Supports two modes:
    - Traditional mode: Provide yaml_content directly
    - Template mode: Provide template_id and variable_values

    Optionally bundles a restart schedule, eliminating the need for a
    follow-up POST /restart-schedule round-trip.
    """

    yaml_content: Optional[str] = None
    template_id: Optional[int] = None
    variable_values: Optional[dict] = None
    restart_schedule: Optional[RestartScheduleRequest] = None


@router.post("/{server_id}", response_model=CreateServerResult)
async def create_server(
    server_id: str,
    create_request: CreateServerRequest,
    db: AsyncSession = Depends(get_db),
    _: UserPublic = Depends(get_current_user),
) -> CreateServerResult:
    """Create a new Minecraft server.

    Supports two modes:
    - Traditional mode: Provide yaml_content directly
    - Template mode: Provide template_id and variable_values

    The restart_schedule field, if present, creates a restart cron job in
    the same operation. DNS is updated as the final step (best-effort).
    """
    spec = CreateServerSpec.model_validate(create_request.model_dump())
    return await create_server_full(db, server_id, spec)
