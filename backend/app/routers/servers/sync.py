from fastapi import APIRouter, Body, Depends

from app.auth.models import UserRole
from app.auth.schemas import UserPublic
from app.servers.api_models import SyncRequest

from ...background_tasks.api_models import TaskAccepted
from ...dependencies import RequireRole
from ...servers.synchronization import submit_sync

router = APIRouter(prefix="/servers", tags=["server-sync"])


@router.post("/sync", response_model=TaskAccepted, status_code=202)
async def sync_servers(
    body: SyncRequest = Body(default_factory=SyncRequest),
    user: UserPublic = Depends(RequireRole(UserRole.OWNER)),
) -> TaskAccepted:
    return await submit_sync(body, user.id)
