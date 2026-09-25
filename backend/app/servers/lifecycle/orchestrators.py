import asyncio
import json
from datetime import UTC, datetime

from aiofiles import os as aioos
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ...configuration.preparation import (
    capture_template_snapshot,
    prepare_template_configuration,
)
from ...cron import get_cron_manager
from ...dns import get_dns_manager
from ...errors import PublicOperationError, log_safe_error
from ...log_monitor import get_log_monitor
from ...logger import get_logger
from ...minecraft import MCInstance, get_docker_mc_manager
from ...minecraft.game_port import validate_game_port_initialization
from ...operation_admission import get_server_write_admission
from ...operations.context import record_phase
from ...operations.coordinator import (
    ResourceClaim,
    ResourceKind,
    get_operation_coordinator,
)
from ...operations.execution import operation_scope
from ...operations.finalization import finalize
from ...templates import (
    TemplateSnapshot,
    get_template_by_id,
)
from ..crud import create_server_record, get_active_server_by_id, mark_server_removed
from ..port_utils import check_port_conflicts, extract_ports_from_yaml
from ..restart_schedule import schedule_auto_restart
from .primitives import (
    cancel_and_wait_for_tasks,
    cancel_restart_cronjobs_for_server,
    close_open_sessions,
    validate_adoption,
)
from .types import CreateServerResult, CreateServerSpec, RemoveServerResult


async def _resolve_yaml_and_metadata(
    db: AsyncSession, spec: CreateServerSpec
) -> tuple[str, TemplateSnapshot | None, dict | None]:
    if spec.yaml_content and spec.template_id:
        raise HTTPException(
            status_code=400,
            detail="请提供 yaml_content 或 template_id，不能同时提供",
        )

    if not spec.yaml_content and spec.template_id is None:
        raise HTTPException(
            status_code=400,
            detail="必须提供 yaml_content 或 template_id",
        )

    if spec.yaml_content is not None:
        return spec.yaml_content, None, None

    if spec.variable_values is None:
        raise HTTPException(
            status_code=400,
            detail="使用模板模式时必须提供 variable_values",
        )

    assert spec.template_id is not None
    template = await get_template_by_id(db, spec.template_id)
    if not template:
        raise HTTPException(status_code=404, detail="模板不存在")

    try:
        configuration = prepare_template_configuration(
            capture_template_snapshot(template), spec.variable_values
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return configuration.yaml_content, configuration.template_snapshot, configuration.variable_values


async def create_server_full(
    db: AsyncSession, server_id: str, spec: CreateServerSpec
) -> CreateServerResult:
    if get_operation_coordinator().global_files_busy():
        raise HTTPException(status_code=423, detail="服务器文件正在恢复或修改，请稍后重试")
    async with get_operation_coordinator().acquire([ResourceClaim(ResourceKind.PORT_ALLOCATION), ResourceClaim(ResourceKind.FILES, server_id)]):
        return await _create_server_with_ports(db, server_id, spec)


async def _create_server_with_ports(
    db: AsyncSession, server_id: str, spec: CreateServerSpec
) -> CreateServerResult:
    logger = get_logger()
    yaml_content, snapshot, vars_dict = await _resolve_yaml_and_metadata(db, spec)

    instance = get_docker_mc_manager().get_instance(server_id)
    if await get_active_server_by_id(db, server_id) is not None or await instance.exists():
        raise HTTPException(
            status_code=409, detail=f"服务器 '{server_id}' 已存在"
        )
    if await aioos.path.exists(instance.get_project_path()) or await aioos.path.islink(instance.get_project_path()):
        raise HTTPException(status_code=409, detail="服务器项目目录已经存在，请先检查目录内容或显式接管")

    try:
        game_port, rcon_port = extract_ports_from_yaml(yaml_content)
        validate_game_port_initialization(yaml_content)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    conflicts = await check_port_conflicts(game_port, rcon_port)
    if conflicts:
        raise HTTPException(
            status_code=409, detail=f"端口冲突: {'; '.join(conflicts)}"
        )

    restart_cronjob_id: str | None = None

    async def write_instance() -> None:
        try:
            await instance.create(yaml_content)
        except FileExistsError as e:
            raise HTTPException(status_code=409, detail=str(e)) from e
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        await create_server_record(
            db,
            server_id,
            template_id=spec.template_id if snapshot else None,
            template_snapshot_json=(
                snapshot.model_dump_json() if snapshot else None
            ),
            variable_values_json=(
                json.dumps(vars_dict) if vars_dict else None
            ),
        )

    try:
        # Cancellation cannot race cleanup against unfinished aiofiles executor writes.
        await finalize(write_instance())
        try:
            await get_log_monitor().start_server(server_id)
        except Exception as e:
            logger.warning(
                f"log_monitor.start_server failed for {server_id}: {e}", exc_info=True)

        if spec.restart_schedule is not None:
            schedule = await schedule_auto_restart(server_id, spec.restart_schedule)
            restart_cronjob_id = schedule.cronjob_id

        try:
            await get_dns_manager().update(db)
        except Exception as e:
            logger.warning(f"dns update failed for {server_id}: {e}", exc_info=True)

        return CreateServerResult(
            server_id=server_id,
            game_port=game_port,
            rcon_port=rcon_port,
            restart_cronjob_id=restart_cronjob_id,
        )

    except (Exception, asyncio.CancelledError):
        await finalize(_rollback_server_creation(db, instance, restart_cronjob_id))
        raise


async def _rollback_server_creation(
    db: AsyncSession, instance: MCInstance, restart_cronjob_id: str | None
) -> None:
    logger = get_logger()
    server_id = instance.get_name()
    failed_steps: list[str] = []

    async def deactivate_record() -> None:
        await db.rollback()
        if await get_active_server_by_id(db, server_id) is not None:
            await mark_server_removed(db, server_id, datetime.now(UTC))

    async def remove_owned_directory() -> None:
        if await aioos.path.exists(instance.get_project_path()) or await aioos.path.islink(instance.get_project_path()):
            await instance.remove()

    steps = []
    if restart_cronjob_id is not None:
        steps.append(("restart_schedule", lambda: get_cron_manager().cancel_cronjob(restart_cronjob_id)))
    steps.extend([
        ("log_monitor", lambda: get_log_monitor().stop_watching(server_id)),
        ("server_record", deactivate_record),
        ("project_directory", remove_owned_directory),
    ])
    for name, action in steps:
        try:
            await action()
        except (Exception, asyncio.CancelledError) as exc:  # noqa: BLE001 - finish every cleanup step and report incomplete recovery
            failed_steps.append(name)
            if isinstance(exc, Exception):
                log_safe_error(exc, f"Server creation cleanup failed ({name})")
            else:
                logger.error("Server creation cleanup was cancelled (%s)", name)
    if failed_steps:
        labels = {"restart_schedule": "重启计划", "log_monitor": "日志监视", "server_record": "服务器记录", "project_directory": "项目目录"}
        raise PublicOperationError(
            f"服务器 '{server_id}' 创建失败且清理未完成（{'、'.join(labels[name] for name in failed_steps)}），"
            "请检查该服务器的目录、登记记录和重启计划后再重试"
        )


async def remove_server_full(
    db: AsyncSession, server_id: str, *, user_id: int | None = None
) -> RemoveServerResult:
    async with operation_scope("server_remove", [server_id], actor_id=user_id):
        return await _remove_server(db, server_id)


async def _remove_server(db: AsyncSession, server_id: str) -> RemoveServerResult:
    with get_server_write_admission().freeze(server_id) as permit:
        instance = get_docker_mc_manager().get_instance(server_id)
        if await instance.created():
            raise HTTPException(
                status_code=409,
                detail=f"服务器 '{server_id}' 的容器仍在运行，请先停止后再删除",
            )

        cancelled_tasks = await cancel_and_wait_for_tasks(server_id)
        get_server_write_admission().require_drained(server_id)
        if await instance.created():
            raise HTTPException(status_code=409, detail="服务器容器仍然存在，请先下线后再删除")

        async with get_operation_coordinator().delete(server_id, permit):
            return await finalize(_remove_drained_server(db, server_id, instance, cancelled_tasks))


async def _remove_drained_server(
    db: AsyncSession, server_id: str, instance: MCInstance, cancelled_tasks: list[str],
) -> RemoveServerResult:
    logger = get_logger()
    await record_phase("removing_server", changed=True)
    now = datetime.now(UTC)
    cancelled_jobs = await cancel_restart_cronjobs_for_server(db, server_id)
    closed_sessions = await close_open_sessions(server_id, now=now)
    try:
        await get_log_monitor().stop_watching(server_id)
    except Exception as e:
        logger.warning(f"log_monitor.stop_watching failed for {server_id}: {e}", exc_info=True)
    await mark_server_removed(db, server_id, now)

    await instance.remove()
    await record_phase("server_removed", changed=True)

    try:
        await get_dns_manager().update(db)
    except Exception as e:
        logger.warning(
            f"dns update failed after removing {server_id}: {e}", exc_info=True)

    return RemoveServerResult(
        server_id=server_id,
        cancelled_restart_cronjob_ids=cancelled_jobs,
        cancelled_background_task_ids=cancelled_tasks,
        closed_sessions=closed_sessions,
    )


async def adopt_server_partial(
    db: AsyncSession, server_id: str, *, game_port: int, rcon_port: int
) -> CreateServerResult:
    if get_operation_coordinator().global_files_busy():
        raise HTTPException(status_code=423, detail="服务器文件正在恢复或修改，请稍后重试")
    async with get_operation_coordinator().acquire([ResourceClaim(ResourceKind.PORT_ALLOCATION), ResourceClaim(ResourceKind.FILES, server_id)]):
        if await get_active_server_by_id(db, server_id) is not None:
            raise HTTPException(status_code=409, detail="服务器已经登记，请刷新服务器列表")
        current_ports = await validate_adoption(db, server_id)
        if current_ports != (game_port, rcon_port):
            raise HTTPException(status_code=409, detail="服务器端口配置已变化，请重新预览接管结果")
        return await _adopt_server_with_ports(db, server_id, game_port=game_port, rcon_port=rcon_port)


async def _adopt_server_with_ports(
    db: AsyncSession, server_id: str, *, game_port: int, rcon_port: int
) -> CreateServerResult:
    # Direct-mode only: template binding can't be inferred from a compose file.
    logger = get_logger()
    await create_server_record(db, server_id)

    try:
        await get_log_monitor().start_server(server_id)
    except Exception as e:
        logger.warning(f"adopt: log_monitor failed for {server_id}: {e}", exc_info=True)

    return CreateServerResult(
        server_id=server_id,
        game_port=game_port,
        rcon_port=rcon_port,
        restart_cronjob_id=None,
    )


async def deactivate_server_partial(
    db: AsyncSession, server_id: str
) -> RemoveServerResult:
    async with operation_scope("server_deactivate", [server_id], require_exists=False):
        with get_server_write_admission().freeze(server_id):
            cancelled_tasks = await cancel_and_wait_for_tasks(server_id)
            get_server_write_admission().require_drained(server_id)
            return await finalize(_deactivate_drained_server(db, server_id, cancelled_tasks))


async def _deactivate_drained_server(
    db: AsyncSession, server_id: str, cancelled_tasks: list[str],
) -> RemoveServerResult:
    logger = get_logger()
    await record_phase("deactivating_server", changed=True)
    now = datetime.now(UTC)
    cancelled_jobs = await cancel_restart_cronjobs_for_server(db, server_id)
    closed_sessions = await close_open_sessions(server_id, now=now)
    try:
        await get_log_monitor().stop_watching(server_id)
    except Exception as e:
        logger.warning(f"deactivate: log_monitor failed for {server_id}: {e}", exc_info=True)
    await mark_server_removed(db, server_id, now)

    return RemoveServerResult(
        server_id=server_id,
        cancelled_restart_cronjob_ids=cancelled_jobs,
        cancelled_background_task_ids=cancelled_tasks,
        closed_sessions=closed_sessions,
    )
