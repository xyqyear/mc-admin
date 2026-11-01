"""Public server read models assembled from Minecraft configuration."""

from ..background_tasks.manager import BackgroundTaskManager
from ..minecraft import MCInstance
from ..operation_admission import ServerWriteAdmission
from ..world.locks import ServerOperationLock
from .api_models import ServerListItem, ServerMaintenance
from .tasks import LIFECYCLE_TASKS


def get_server_maintenance(
    server_ids: list[str], admission: ServerWriteAdmission,
    tasks: BackgroundTaskManager, locks: ServerOperationLock,
) -> dict[str, ServerMaintenance]:
    active = {}
    for task in tasks.get_active_tasks():
        if task.task_type in LIFECYCLE_TASKS:
            active.setdefault(task.server_id, task)
    result = {}
    for server_id in server_ids:
        reason = admission.recovery_reason(server_id)
        task = active.get(server_id)
        holder = locks.get_holder(server_id)
        if reason is not None:
            value = ServerMaintenance(active=True, kind="recovery", description=reason)
        elif task is not None:
            value = ServerMaintenance(active=True, kind=task.task_type.value,
                                      description=task.message or task.name, task_id=task.task_id)
        elif admission.is_frozen(server_id):
            value = ServerMaintenance(active=True, kind="remove", description="删除服务器")
        elif holder is not None:
            value = ServerMaintenance(active=True, kind=holder.kind.value, description=holder.description)
        else:
            value = ServerMaintenance()
        result[server_id] = value
    return result


async def get_server_list_item(instance: MCInstance) -> ServerListItem:
    """Helper to get basic server info for a single instance"""
    server_id = instance.get_name()

    # Get only basic server info
    server_info = await instance.get_server_info()

    return ServerListItem(
        id=server_id,
        name=server_info.name,
        serverType=server_info.server_type,
        gameVersion=server_info.game_version,
        gamePort=server_info.game_port,
        maxMemoryBytes=server_info.max_memory_bytes,
        rconPort=server_info.rcon_port,
        javaVersion=server_info.java_version,
    )
