"""Server lifecycle orchestrators.

Each orchestrator chains the primitives needed for a high-level operation
(create, remove, sync-driven adopt/deactivate). Rollback uses compensation,
not SQL transactions — see types.py and the comment at create_server_full
for the model.

Implicit contract: between the filesystem write in create_server_full and
the trigger of rollback, no phase brings containers up. If a future change
adds a "create + start" combined flow, the rollback must be revised because
instance.remove() raises when instance.created() is true.
"""

import json
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ...cron import cron_manager
from ...dns import simple_dns_manager
from ...log_monitor import log_monitor
from ...logger import logger
from ...minecraft import docker_mc_manager
from ...routers.servers.restart_schedule import schedule_auto_restart
from ...templates import (
    TemplateSnapshot,
    deserialize_variable_definitions_json,
    get_template_by_id,
)
from ...templates.manager import TemplateManager
from ..crud import create_server_record, mark_server_removed
from ..port_utils import check_port_conflicts, extract_ports_from_yaml
from .primitives import (
    cancel_and_wait_for_tasks,
    cancel_restart_cronjobs_for_server,
    close_open_sessions,
)
from .types import CreateServerResult, CreateServerSpec, RemoveServerResult


async def _resolve_yaml_and_metadata(
    db: AsyncSession, spec: CreateServerSpec
) -> tuple[str, Optional[TemplateSnapshot], Optional[dict]]:
    """Validate the spec and resolve YAML content + optional template metadata.

    Pure: no filesystem or DB side effects. Raises HTTPException on
    user-facing validation failure.
    """
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

    # Template mode
    if spec.variable_values is None:
        raise HTTPException(
            status_code=400,
            detail="使用模板模式时必须提供 variable_values",
        )

    assert spec.template_id is not None
    template = await get_template_by_id(db, spec.template_id)
    if not template:
        raise HTTPException(status_code=404, detail="模板不存在")

    user_variables = deserialize_variable_definitions_json(
        template.variable_definitions_json
    )

    errors = TemplateManager.validate_variable_values(user_variables, spec.variable_values)
    if errors:
        raise HTTPException(status_code=400, detail=errors)

    try:
        yaml_content = TemplateManager.render_yaml(
            template.yaml_template, spec.variable_values
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    snapshot = TemplateSnapshot(
        template_id=template.id,
        template_name=template.name,
        yaml_template=template.yaml_template,
        variable_definitions=deserialize_variable_definitions_json(
            template.variable_definitions_json
        ),
        snapshot_time=datetime.now(timezone.utc).isoformat(),
    )

    return yaml_content, snapshot, spec.variable_values


async def create_server_full(
    db: AsyncSession, server_id: str, spec: CreateServerSpec
) -> CreateServerResult:
    """Create a server in one bundled operation: filesystem + DB row + log
    monitor + optional restart schedule + DNS update.

    Any failure after the filesystem write triggers compensation in reverse
    order. DNS failures are best-effort and do not roll back.
    """
    yaml_content, snapshot, vars_dict = await _resolve_yaml_and_metadata(db, spec)

    instance = docker_mc_manager.get_instance(server_id)
    if await instance.exists():
        raise HTTPException(
            status_code=409, detail=f"服务器 '{server_id}' 已存在"
        )

    try:
        game_port, rcon_port = extract_ports_from_yaml(yaml_content)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    conflicts = await check_port_conflicts(game_port, rcon_port)
    if conflicts:
        raise HTTPException(
            status_code=409, detail=f"端口冲突: {'; '.join(conflicts)}"
        )

    try:
        await instance.create(yaml_content)
    except FileExistsError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    restart_cronjob_id: Optional[str] = None
    row_inserted = False

    try:
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
        row_inserted = True

        try:
            await log_monitor.start_server(server_id)
        except Exception as e:
            logger.warning(
                f"log_monitor.start_server failed for {server_id}: {e}"
            )

        if spec.restart_schedule is not None:
            schedule = await schedule_auto_restart(server_id, spec.restart_schedule)
            restart_cronjob_id = schedule.cronjob_id

        try:
            await simple_dns_manager.update()
        except Exception as e:
            logger.warning(f"dns update failed for {server_id}: {e}")

        return CreateServerResult(
            server_id=server_id,
            game_port=game_port,
            rcon_port=rcon_port,
            restart_cronjob_id=restart_cronjob_id,
        )

    except Exception:
        if restart_cronjob_id is not None:
            try:
                await cron_manager.cancel_cronjob(restart_cronjob_id)
            except Exception as e:
                logger.error(
                    f"rollback: failed to cancel cronjob "
                    f"{restart_cronjob_id} for {server_id}: {e}"
                )
        try:
            await log_monitor.stop_watching(server_id)
        except Exception as e:
            logger.error(
                f"rollback: stop_watching failed for {server_id}: {e}"
            )
        if row_inserted:
            try:
                await mark_server_removed(
                    db, server_id, datetime.now(timezone.utc)
                )
            except Exception as e:
                logger.error(
                    f"rollback: failed to mark {server_id} removed: {e}"
                )
        try:
            await instance.remove()
        except Exception as e:
            logger.error(f"rollback: failed to remove {server_id}: {e}")
        raise


async def remove_server_full(
    db: AsyncSession, server_id: str
) -> RemoveServerResult:
    """Remove a server in one bundled operation: refuse if containers up,
    cancel-and-wait background tasks, cancel restart cronjobs, close
    sessions, stop log monitor, mark row REMOVED, rmtree, update DNS.

    Once past the containers-up gate, partial failures are not rolled back —
    removal is destructive by design.
    """
    instance = docker_mc_manager.get_instance(server_id)
    if await instance.created():
        raise HTTPException(
            status_code=409,
            detail=f"服务器 '{server_id}' 的容器仍在运行，请先停止后再删除",
        )

    cancelled_tasks = await cancel_and_wait_for_tasks(server_id)

    now = datetime.now(timezone.utc)
    cancelled_jobs = await cancel_restart_cronjobs_for_server(db, server_id)
    closed_sessions = await close_open_sessions(server_id, now=now)
    try:
        await log_monitor.stop_watching(server_id)
    except Exception as e:
        logger.warning(f"log_monitor.stop_watching failed for {server_id}: {e}")
    await mark_server_removed(db, server_id, now)

    await instance.remove()

    try:
        await simple_dns_manager.update()
    except Exception as e:
        logger.warning(
            f"dns update failed after removing {server_id}: {e}"
        )

    return RemoveServerResult(
        server_id=server_id,
        cancelled_restart_cronjob_ids=cancelled_jobs,
        cancelled_background_task_ids=cancelled_tasks,
        closed_sessions=closed_sessions,
    )


async def adopt_server_partial(
    db: AsyncSession, server_id: str, *, game_port: int, rcon_port: int
) -> CreateServerResult:
    """For directories that exist on disk but have no ACTIVE Server row.

    Validation is performed by the caller (sync endpoint) via
    validate_adoption — this function trusts that the compose has already
    been validated and the ports are not in conflict.

    NOTE: adopted rows are direct-mode only. We cannot infer template_id or
    template_snapshot from a compose file alone. The sync UI must surface
    this so OWNER users are not surprised that their adopted server has no
    template binding.
    """
    await create_server_record(db, server_id)

    try:
        await log_monitor.start_server(server_id)
    except Exception as e:
        logger.warning(f"adopt: log_monitor failed for {server_id}: {e}")

    return CreateServerResult(
        server_id=server_id,
        game_port=game_port,
        rcon_port=rcon_port,
        restart_cronjob_id=None,
    )


async def deactivate_server_partial(
    db: AsyncSession, server_id: str
) -> RemoveServerResult:
    """For ACTIVE rows whose directory no longer exists on disk.

    Skips Phase 0 (no container to check) and the filesystem rmtree.
    Still cancels + waits for background tasks because a task may have
    been mid-write when the directory vanished.
    """
    cancelled_tasks = await cancel_and_wait_for_tasks(server_id)

    now = datetime.now(timezone.utc)
    cancelled_jobs = await cancel_restart_cronjobs_for_server(db, server_id)
    closed_sessions = await close_open_sessions(server_id, now=now)
    try:
        await log_monitor.stop_watching(server_id)
    except Exception as e:
        logger.warning(f"deactivate: log_monitor failed for {server_id}: {e}")
    await mark_server_removed(db, server_id, now)

    return RemoveServerResult(
        server_id=server_id,
        cancelled_restart_cronjob_ids=cancelled_jobs,
        cancelled_background_task_ids=cancelled_tasks,
        closed_sessions=closed_sessions,
    )
