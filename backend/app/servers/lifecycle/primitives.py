import asyncio
from datetime import datetime

import yaml
from sqlalchemy.ext.asyncio import AsyncSession

from ...background_tasks import task_manager
from ...cron import cron_manager
from ...cron.crud import get_active_restart_cronjobs_for_server
from ...db.database import get_async_session
from ...logger import logger
from ...minecraft import docker_mc_manager
from ...minecraft.compose import MCComposeFile
from ...minecraft.docker.compose_file import ComposeFile
from ...players.crud import (
    end_all_open_sessions_on_server,
    get_all_open_sessions_on_server,
)
from ..crud import get_server_db_id
from ..port_utils import check_port_conflicts


async def cancel_and_wait_for_tasks(
    server_id: str, *, timeout: float = 30.0
) -> list[str]:
    # cancel() only sets a flag; awaiting futures closes the race against rmtree.
    tasks = task_manager.get_tasks_by_server_id(server_id)
    if not tasks:
        return []

    task_ids = [t.task_id for t in tasks]
    futures: list[asyncio.Future] = []

    for tid in task_ids:
        await task_manager.cancel(tid)
        fut = task_manager.get_future(tid)
        if fut is not None and not fut.done():
            futures.append(fut)

    if futures:
        done, pending = await asyncio.wait(futures, timeout=timeout)
        if pending:
            logger.warning(
                f"cancel_and_wait_for_tasks: {len(pending)} task(s) for "
                f"server '{server_id}' did not settle within {timeout}s"
            )

    return task_ids


async def cancel_restart_cronjobs_for_server(
    db: AsyncSession, server_id: str
) -> list[str]:
    jobs = await get_active_restart_cronjobs_for_server(db, server_id)
    cancelled: list[str] = []
    for job in jobs:
        try:
            await cron_manager.cancel_cronjob(job.cronjob_id)
            cancelled.append(job.cronjob_id)
        except Exception as e:
            logger.error(
                f"Failed to cancel restart cronjob {job.cronjob_id} for "
                f"server '{server_id}': {e}"
            )
    return cancelled


async def close_open_sessions(server_id: str, *, now: datetime) -> int:
    async with get_async_session() as session:
        server_db_id = await get_server_db_id(session, server_id)
        if server_db_id is None:
            return 0
        return await end_all_open_sessions_on_server(session, server_db_id, now)


async def validate_adoption(
    db: AsyncSession, server_id: str
) -> tuple[int, int]:
    instance = docker_mc_manager.get_instance(server_id)
    try:
        compose_content = await instance.get_compose_file()
    except FileNotFoundError as e:
        raise ValueError(f"未找到 compose 文件: {e}")

    try:
        compose_obj = ComposeFile.from_dict(yaml.safe_load(compose_content))
        mc_compose = MCComposeFile(compose_obj)
    except ValueError:
        raise
    except Exception as e:
        raise ValueError(f"无法解析 compose 文件: {e}")

    if mc_compose.get_server_name() != server_id:
        raise ValueError(
            f"compose 中的服务器名 '{mc_compose.get_server_name()}' "
            f"与目录名 '{server_id}' 不一致"
        )

    game_port = mc_compose.get_game_port()
    rcon_port = mc_compose.get_rcon_port()

    conflicts = await check_port_conflicts(
        game_port, rcon_port, exclude_server_id=server_id
    )
    if conflicts:
        raise ValueError(f"端口冲突: {'; '.join(conflicts)}")

    return game_port, rcon_port


async def preview_deactivation(
    db: AsyncSession, server_id: str
) -> tuple[int, int]:
    cronjobs = await get_active_restart_cronjobs_for_server(db, server_id)
    cronjob_count = len(cronjobs)

    server_db_id = await get_server_db_id(db, server_id)
    if server_db_id is None:
        return cronjob_count, 0

    open_sessions = await get_all_open_sessions_on_server(db, server_db_id)
    return cronjob_count, len(open_sessions)
