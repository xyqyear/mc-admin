from fastapi import APIRouter, Depends

from app.auth.schemas import UserPublic

from ...background_tasks.api_models import TaskAccepted
from ...dependencies import get_current_user
from ...servers.api_models import ServerOperation
from ...servers.tasks import submit_lifecycle

router = APIRouter(
    prefix="/servers",
    tags=["server-operations"],
)


@router.post("/{server_id}/operations", response_model=TaskAccepted, status_code=202)
async def server_operation(
    server_id: str,
    operation: ServerOperation,
    user: UserPublic = Depends(get_current_user),
):
    return await submit_lifecycle(server_id, operation.action.lower(), user.id)
