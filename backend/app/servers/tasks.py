from collections.abc import AsyncGenerator

from fastapi import HTTPException

from ..background_tasks import TaskProgress, TaskType, get_task_manager
from ..background_tasks.api_models import TaskAccepted
from ..config import get_settings
from ..configuration.preparation import ServerConfiguration
from ..db.database import get_async_session
from ..minecraft import get_docker_mc_manager
from ..operation_admission import get_server_write_admission
from ..operations.journal_types import ResourceReference
from ..self_check.constants import SERVER_CREATED_TRIGGER
from ..self_check.events import schedule_self_check_event
from ..world.locks import get_server_operation_lock
from .commands import ServerAction, ServerCommands
from .lifecycle import CreateServerSpec, create_server_full, remove_server_full
from .lifecycle.orchestrators import prepare_server_creation
from .references import ServerRef, resolve_server_ref

LIFECYCLE_TASKS = frozenset({
    TaskType.SERVER_START, TaskType.SERVER_UP, TaskType.SERVER_RESTART,
    TaskType.SERVER_STOP, TaskType.SERVER_DOWN, TaskType.SERVER_REMOVE, TaskType.SERVER_CREATE,
})

ACTION_NAMES = {
    "start": "启动服务器", "up": "启动服务器", "restart": "重启服务器",
    "stop": "停止服务器", "down": "下线服务器", "remove": "删除服务器",
}
ACTION_MESSAGES = {
    "start": "正在启动容器", "up": "正在准备镜像和容器",
    "restart": "正在重启服务器", "stop": "正在等待服务器停止",
    "down": "正在停止服务器并移除容器", "remove": "正在检查任务并删除服务器",
}


async def lifecycle_task(
    reference: ServerRef, action: ServerAction | str, actor_id: int,
) -> AsyncGenerator[TaskProgress]:
    yield TaskProgress(message=ACTION_MESSAGES[action])
    if action == "remove":
        async with get_async_session() as session:
            result = await remove_server_full(session, reference.server_id, user_id=actor_id)
        data = result.model_dump(mode="json")
    elif action in ("start", "up", "restart", "stop", "down"):
        await ServerCommands().execute(reference.server_id, action, actor_id=actor_id, reference=reference)
        data = {"server_id": reference.server_id, "action": action}
    else:
        raise HTTPException(status_code=400, detail="不支持的服务器操作")
    yield TaskProgress(progress=100, message=f"{ACTION_NAMES[action]}操作完成", result=data)


async def submit_lifecycle(server_id: str, action: str, actor_id: int) -> TaskAccepted:
    if action not in ACTION_NAMES:
        raise HTTPException(status_code=400, detail="不支持的服务器操作")
    get_server_write_admission().check(server_id, allow_recovery_stop=action in {"stop", "down"})
    async with get_async_session() as session:
        reference = await resolve_server_ref(session, server_id, servers_root=get_settings().server_path)
    if action in ("start", "up", "restart") and get_server_operation_lock().is_locked(server_id):
        raise HTTPException(status_code=423, detail="服务器正在维护，请等待操作完成")
    if action == "remove" and await get_docker_mc_manager().get_instance(server_id).created():
        raise HTTPException(status_code=409, detail="服务器容器仍然存在，请先下线后再删除")
    submitted = await get_task_manager().submit_durable(
        TaskType(f"server_{action}"), f"{ACTION_NAMES[action]} {server_id}",
        lifecycle_task(reference, action, actor_id), server_id=server_id,
        actor_id=actor_id, server_refs=(reference,), cancellable=False,
        exclusive_key=f"server-lifecycle:{server_id}",
    )
    return TaskAccepted(task_id=submitted.task_id)


async def create_task(
    server_id: str, spec: CreateServerSpec, configuration: ServerConfiguration, actor_id: int,
) -> AsyncGenerator[TaskProgress]:
    yield TaskProgress(message="正在创建服务器并配置重启计划和连接信息")
    async with get_async_session() as session:
        result = await create_server_full(session, server_id, spec, configuration=configuration)
    schedule_self_check_event(SERVER_CREATED_TRIGGER, actor_id)
    yield TaskProgress(progress=100, message="服务器创建完成", result=result.model_dump(mode="json"))


async def submit_creation(server_id: str, spec: CreateServerSpec, actor_id: int) -> TaskAccepted:
    async with get_async_session() as session:
        configuration = await prepare_server_creation(session, server_id, spec)
    submitted = await get_task_manager().submit_durable(
        TaskType.SERVER_CREATE, f"创建服务器 {server_id}",
        create_task(server_id, spec.model_copy(deep=True), configuration, actor_id),
        server_id=server_id, server_refs=(), resources=(ResourceReference("files", path=server_id),),
        actor_id=actor_id, cancellable=False, exclusive_key=f"server-lifecycle:{server_id}",
    )
    return TaskAccepted(task_id=submitted.task_id)
