from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.schemas import UserPublic
from app.configuration.api_models import ComposeConfig, RebuildResponse

from ...background_tasks import TaskType, get_task_manager
from ...configuration.application import check_rebuild_available, rebuild_server_task
from ...configuration.preparation import ServerConfiguration
from ...configuration.state import read_configuration_state
from ...db.database import get_db
from ...dependencies import get_current_user
from ...minecraft import get_docker_mc_manager
from .admission import admit_server_write

router = APIRouter(
    prefix="/servers",
    tags=["server-compose"],
    dependencies=[Depends(admit_server_write)],
)


@router.get("/{server_id}/compose")
async def get_server_compose(server_id: str, db: AsyncSession = Depends(get_db), _: UserPublic = Depends(get_current_user)):
    state = await read_configuration_state(db, server_id, get_docker_mc_manager().servers_path)
    return {"yaml_content": state.yaml_content, "version": state.version}


@router.post("/{server_id}/compose", response_model=RebuildResponse)
async def update_server_compose(
    server_id: str,
    compose_config: ComposeConfig,
    db: AsyncSession = Depends(get_db),
    _: UserPublic = Depends(get_current_user),
):
    """Update the Docker Compose configuration for a specific server.

    Returns a task_id for tracking the rebuild progress.
    """
    instance = get_docker_mc_manager().get_instance(server_id)

    if not await instance.exists():
        raise HTTPException(status_code=404, detail=f"服务器 '{server_id}' 不存在")

    current = await read_configuration_state(db, server_id, get_docker_mc_manager().servers_path)
    current.check_version(compose_config.expected_version)
    if current.template_id:
        raise HTTPException(
            status_code=400,
            detail="该服务器是使用模板创建的，请使用模板配置接口进行修改",
        )

    check_rebuild_available(server_id)
    configuration = ServerConfiguration(compose_config.yaml_content, expected_version=compose_config.expected_version)
    result = await get_task_manager().submit_durable(
        task_type=TaskType.SERVER_REBUILD,
        name=f"重建 {server_id}",
        task_generator=rebuild_server_task(server_id, configuration),
        server_id=server_id,
        cancellable=False,
        actor_id=_.id,
        configuration_version=configuration.fingerprint,
    )

    return RebuildResponse(task_id=result.task_id)
