from fastapi import APIRouter, Depends

from app.auth.schemas import UserPublic

from ...background_tasks import get_task_manager
from ...background_tasks.api_models import TaskAccepted
from ...dependencies import get_current_user
from ...operation_admission import get_server_write_admission
from ...servers.api_models import ServerOperation
from ...servers.tasks import LIFECYCLE_TASKS, submit_lifecycle
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
    active = next((task for task in get_task_manager().get_tasks_by_server_id(server_id)
                   if task.task_type in LIFECYCLE_TASKS), None)
    if active is not None:
        return {"active": True, "kind": active.task_type.value,
                "description": active.message or active.name, "task_id": active.task_id}
    if get_server_write_admission().is_frozen(server_id):
        return {"active": True, "kind": "remove", "description": "删除服务器"}
    holder = get_server_operation_lock().get_holder(server_id)
    return {
        "active": holder is not None,
        "kind": holder.kind.value if holder else None,
        "description": holder.description if holder else None,
    }


@router.post("/{server_id}/operations", response_model=TaskAccepted, status_code=202)
async def server_operation(
    server_id: str,
    operation: ServerOperation,
    user: UserPublic = Depends(get_current_user),
):
    return await submit_lifecycle(server_id, operation.action.lower(), user.id)
