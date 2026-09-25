"""Server creation API router supporting both traditional YAML and template modes."""


from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.schemas import UserPublic
from app.servers.api_models import CreateServerRequest

from ...db.database import get_db
from ...dependencies import get_current_user
from ...self_check.constants import SERVER_CREATED_TRIGGER
from ...self_check.events import schedule_self_check_event
from ...servers.lifecycle import (
    CreateServerResult,
    CreateServerSpec,
    create_server_full,
)
from .admission import admit_server_write

router = APIRouter(
    prefix="/servers",
    tags=["server-creation"],
    dependencies=[Depends(admit_server_write)],
)


@router.post("/{server_id}", response_model=CreateServerResult)
async def create_server(
    server_id: str,
    create_request: CreateServerRequest,
    db: AsyncSession = Depends(get_db),
    user: UserPublic = Depends(get_current_user),
) -> CreateServerResult:
    """Create a new Minecraft server.

    Supports two modes:
    - Traditional mode: Provide yaml_content directly
    - Template mode: Provide template_id and variable_values

    The restart_schedule field, if present, creates a restart cron job in
    the same operation. DNS is updated as the final step (best-effort).
    """
    spec = CreateServerSpec.model_validate(create_request.model_dump())
    result = await create_server_full(db, server_id, spec)
    schedule_self_check_event(SERVER_CREATED_TRIGGER, user.id)
    return result
