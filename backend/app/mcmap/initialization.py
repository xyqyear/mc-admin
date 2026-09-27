from collections.abc import AsyncGenerator
from contextlib import aclosing
from pathlib import Path

import aiofiles.os as aioos

from ..background_tasks import TaskProgress, TaskType, get_task_manager
from ..background_tasks.api_models import TaskAccepted
from ..errors import PublicOperationError, log_safe_error, public_error_message
from ..files.resources import path_claims, require_same_claims
from ..logger import get_logger
from ..minecraft import get_docker_mc_manager
from ..operations.context import current_execution, record_phase
from ..operations.coordinator import (
    ResourceClaim,
    ResourceKind,
    get_operation_coordinator,
)
from ..operations.execution import operation_scope, settle_before_release
from ..operations.finalization import finalize
from ..operations.journal_types import OperationState
from ..utils import async_fs
from . import runner as mcmap_runner
from .cache import ServerMapCache
from .events import (
    MCMAP_DOWNLOAD_CLIENT_EVENT_ADAPTER,
    MCMAP_GEN_PALETTE_EVENT_ADAPTER,
    MCMapDownloadClientResultEvent,
    MCMapErrorEvent,
    MCMapGenPaletteResultEvent,
    MCMapProgressEvent,
)
from .ownership import require_usable_cache
from .palette import (
    discover_level_dat,
    discover_mods_dir,
    palette_is_current,
    write_palette_hash,
)
from .types import InitEvent, MCMapError


async def _clear_prerequisite_cache(cache: ServerMapCache) -> None:
    for path in (cache.client_jar, cache.palette_json, cache.palette_hash_file):
        try:
            await aioos.unlink(path)
        except FileNotFoundError:
            pass


async def initialize_events(
    server_id: str,
    *,
    force: bool = False,
    actor_id: int | None = None,
) -> AsyncGenerator[InitEvent]:
    instance = get_docker_mc_manager().get_instance(server_id)
    data = instance.get_data_path()

    async def claims_for_cache():
        files = await path_claims(data.parent, [data / ".mcmap"], server_id=server_id)
        return (*files, ResourceClaim(ResourceKind.MAP_CACHE, server_id))

    claims = await claims_for_cache()
    complete: InitEvent | None = None
    async with (
        operation_scope("map_initialize", [server_id], actor_id=actor_id, claims=claims),
        get_operation_coordinator().acquire(claims),
        settle_before_release(),
    ):
        require_same_claims(claims, await claims_for_cache())
        await require_usable_cache(server_id)
        await record_phase("initializing_map", changed=True)
        async with aclosing(_initialize_owned_stream(server_id, force=force)) as events:
            async for chunk in events:
                event = chunk.model_dump()
                if event.get("stage") == "complete" or event.get("phase") == "error":
                    complete = chunk
                    if event.get("phase") == "error" and (execution := current_execution()) is not None:
                        execution.outcome = OperationState.FAILED
                else:
                    yield chunk
    if complete is not None:
        yield complete


async def _initialize_owned_stream(
    server_id: str,
    *,
    force: bool = False,
) -> AsyncGenerator[InitEvent]:
    logger = get_logger()
    instance = get_docker_mc_manager().get_instance(server_id)
    data_path = instance.get_data_path()
    cache = ServerMapCache(data_path=data_path)
    await async_fs.resolve_inside(data_path, cache.cache_dir)
    await finalize(cache.ensure_dir(cache.cache_dir))

    if force:
        try:
            await finalize(_clear_prerequisite_cache(cache))
        except OSError as e:
            log_safe_error(e, "清理地图缓存失败")
            yield InitEvent.model_validate(
                {
                    "stage": "client",
                    "phase": "error",
                    "message": public_error_message(e),
                }
            )
            return

    try:
        compose = await instance.get_compose_obj()
        version = compose.get_game_version()
    except Exception as e:  # noqa: BLE001 - configuration failures need safe public errors
        log_safe_error(e, "初始化地图时无法解析服务器配置")
        yield InitEvent.model_validate(
            {
                "stage": "client",
                "phase": "error",
                "message": public_error_message(e),
            }
        )
        return

    # Stage 1: client jar
    if await aioos.path.exists(cache.client_jar):
        yield InitEvent.model_validate(
            {"stage": "client", "phase": "done", "percent": 100, "cached": True}
        )
    else:
        yield InitEvent.model_validate({"stage": "client", "phase": "starting", "percent": 0})
        try:
            async with mcmap_runner.download_client(
                version, cache.client_jar, owned_by=data_path
            ) as proc:
                async for event in proc.events(MCMAP_DOWNLOAD_CLIENT_EVENT_ADAPTER):
                    if isinstance(event, MCMapProgressEvent):
                        if event.phase == "downloading":
                            total = event.total or 0
                            got = event.bytes or 0
                            pct = (got / total * 100) if total else 0
                            yield InitEvent.model_validate(
                                {
                                    "stage": "client",
                                    "phase": "downloading",
                                    "percent": pct,
                                    "message": f"正在下载 {version}（{got} / {total} 字节）",
                                }
                            )
                        elif event.phase == "verified":
                            yield InitEvent.model_validate(
                                {
                                    "stage": "client",
                                    "phase": "verifying",
                                    "percent": 100,
                                }
                            )
                    elif isinstance(event, MCMapDownloadClientResultEvent):
                        yield InitEvent.model_validate(
                            {
                                "stage": "client",
                                "phase": "done",
                                "percent": 100,
                                "cached": False,
                            }
                        )
                    elif isinstance(event, MCMapErrorEvent):
                        log_safe_error(MCMapError(event.message), "地图客户端下载失败")
                        yield InitEvent.model_validate(
                            {
                                "stage": "client",
                                "phase": "error",
                                "message": "地图客户端下载失败，请稍后重试",
                            }
                        )
                        return
            if proc.returncode not in (0, None):
                logger.error("地图客户端下载失败: exit_code=%s", proc.returncode)
                yield InitEvent.model_validate(
                    {
                        "stage": "client",
                        "phase": "error",
                        "message": "地图客户端下载失败，请稍后重试",
                    }
                )
                return
        except Exception as e:  # noqa: BLE001 - adapter exception values are not public output
            log_safe_error(e, "地图客户端下载失败")
            yield InitEvent.model_validate({"stage": "client", "phase": "error", "message": public_error_message(e)})
            return

    # Stage 2: palette
    mods_dir = await discover_mods_dir(data_path)
    if await palette_is_current(cache, version, mods_dir):
        yield InitEvent.model_validate(
            {"stage": "palette", "phase": "done", "percent": 100, "cached": True}
        )
        yield InitEvent.model_validate({"stage": "complete"})
        return

    yield InitEvent.model_validate({"stage": "palette", "phase": "starting", "percent": 0})
    packs: list[Path] = []
    if mods_dir is not None:
        packs.append(mods_dir)
    packs.append(cache.client_jar)
    level_dat = await discover_level_dat(data_path)

    try:
        async with mcmap_runner.gen_palette(
            packs,
            cache.palette_json,
            level_dat=level_dat,
            owned_by=data_path,
        ) as proc:
            async for event in proc.events(MCMAP_GEN_PALETTE_EVENT_ADAPTER):
                if isinstance(event, MCMapProgressEvent):
                    if event.phase == "pack_loaded":
                        idx = event.index or 0
                        total = event.total or 1
                        pct = (idx / total * 100) if total else 0
                        path_str = event.path or ""
                        yield InitEvent.model_validate(
                            {
                                "stage": "palette",
                                "phase": "pack_loaded",
                                "percent": pct,
                                "message": f"正在加载 {Path(path_str).name}（{idx} / {total}）",
                            }
                        )
                    elif event.phase == "packs_done":
                        yield InitEvent.model_validate(
                            {
                                "stage": "palette",
                                "phase": "resolving",
                                "percent": 100,
                            }
                        )
                elif isinstance(event, MCMapGenPaletteResultEvent):
                    await finalize(write_palette_hash(cache, version, mods_dir))
                    yield InitEvent.model_validate(
                        {
                            "stage": "palette",
                            "phase": "done",
                            "percent": 100,
                            "cached": False,
                        }
                    )
                elif isinstance(event, MCMapErrorEvent):
                    log_safe_error(MCMapError(event.message), "地图调色板生成失败")
                    yield InitEvent.model_validate(
                        {
                            "stage": "palette",
                            "phase": "error",
                            "message": "地图调色板生成失败，请稍后重试",
                        }
                    )
                    return
        if proc.returncode not in (0, None):
            logger.error("地图调色板生成失败: exit_code=%s", proc.returncode)
            yield InitEvent.model_validate(
                {
                    "stage": "palette",
                    "phase": "error",
                    "message": "地图调色板生成失败，请稍后重试",
                }
            )
            return
    except Exception as e:  # noqa: BLE001 - adapter exception values are not public output
        log_safe_error(e, "地图调色板生成失败")
        yield InitEvent.model_validate({"stage": "palette", "phase": "error", "message": public_error_message(e)})
        return

    yield InitEvent.model_validate({"stage": "complete"})



async def initialize_task(server_id: str, force: bool, actor_id: int) -> AsyncGenerator[TaskProgress]:
    stages: dict[str, dict] = {}
    async with aclosing(initialize_events(server_id, force=force, actor_id=actor_id)) as events:
        async for event in events:
            if event.phase == "error":
                raise PublicOperationError(event.message or "地图初始化失败")
            if event.stage == "complete":
                yield TaskProgress(progress=100, message="地图初始化完成", result={"stages": stages})
            else:
                stages[event.stage] = event.model_dump(mode="json")
                label = "正在准备地图客户端" if event.stage == "client" else "正在生成地图调色板"
                progress = ((event.percent or 0) / 2 + (50 if event.stage == "palette" else 0)) if event.percent is not None else None
                yield TaskProgress(progress=progress, message=event.message or label, result={"stages": dict(stages)})


async def submit_initialization(server_id: str, force: bool, actor_id: int) -> TaskAccepted:
    instance = get_docker_mc_manager().get_instance(server_id)
    data = instance.get_data_path()
    files = await path_claims(data.parent, [data / ".mcmap"], server_id=server_id)
    claims = (*files, ResourceClaim(ResourceKind.MAP_CACHE, server_id))
    submitted = await get_task_manager().submit_durable(
        TaskType.MAP_INITIALIZE, f"初始化地图 {server_id}", initialize_task(server_id, force, actor_id),
        server_id=server_id, claims=claims, actor_id=actor_id, exclusive_key=f"map-initialize:{server_id}",
    )
    return TaskAccepted(task_id=submitted.task_id)
