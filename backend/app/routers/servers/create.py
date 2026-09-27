from fastapi import APIRouter, Depends

from app.auth.schemas import UserPublic
from app.servers.api_models import CreateServerRequest

from ...background_tasks.api_models import TaskAccepted
from ...dependencies import get_current_user
from ...servers.lifecycle import CreateServerSpec
from ...servers.tasks import submit_creation
from .admission import admit_server_write

router = APIRouter(
    prefix="/servers", tags=["server-creation"],
    dependencies=[Depends(admit_server_write)],
)


@router.post("/{server_id}", response_model=TaskAccepted, status_code=202)
async def create_server(
    server_id: str, create_request: CreateServerRequest,
    user: UserPublic = Depends(get_current_user),
) -> TaskAccepted:
    return await submit_creation(server_id, CreateServerSpec.model_validate(create_request.model_dump()), user.id)
