from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.schemas import UserPublic

from ...db.database import get_db
from ...dependencies import get_current_user
from ...minecraft import get_docker_mc_manager
from ...operation_admission import get_server_write_admission
from ...servers.api_models import ServerOperation
from ...servers.commands import ServerCommands
from ...servers.lifecycle import RemoveServerResult, remove_server_full
from ...world.locks import get_server_operation_lock

router = APIRouter(
    prefix="/servers",
    tags=["server-operations"],
)


@router.get("/{server_id}/maintenance")
async def server_maintenance(
    server_id: str, _: UserPublic = Depends(get_current_user)
):
    reason = get_server_write_admission().recovery_reason(server_id)
    if reason is not None:
        return {"active": True, "kind": "recovery", "description": reason}
    if get_server_write_admission().is_frozen(server_id):
        return {"active": True, "kind": "remove", "description": "删除服务器"}
    holder = get_server_operation_lock().get_holder(server_id)
    return {
        "active": holder is not None,
        "kind": holder.kind.value if holder else None,
        "description": holder.description if holder else None,
    }


@router.post("/{server_id}/operations")
async def server_operation(
    server_id: str,
    operation: ServerOperation,
    db: AsyncSession = Depends(get_db),
    user: UserPublic = Depends(get_current_user),
):
    """Perform operations on a server (start, stop, restart, up, down, remove).

    For action=remove, returns a RemoveServerResult with counts of cancelled
    cronjobs and closed sessions. For other actions, returns a simple
    message object.
    """
    instance = get_docker_mc_manager().get_instance(server_id)

    from .admission import _require_registered

    await _require_registered(server_id)

    if not await instance.exists():
        raise HTTPException(status_code=404, detail=f"Server '{server_id}' not found")

    action = operation.action.lower()

    if action in ("start", "up", "restart", "stop", "down"):
        await ServerCommands().execute(server_id, action, actor_id=user.id)
    elif action == "remove":
        result: RemoveServerResult = await remove_server_full(db, server_id, user_id=user.id)
        return result
    else:
        raise HTTPException(status_code=400, detail=f"Invalid operation: {action}")

    return {"message": f"Server '{server_id}' {action} operation completed"}
