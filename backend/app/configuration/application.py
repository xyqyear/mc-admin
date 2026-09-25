import asyncio
from collections.abc import AsyncGenerator
from contextlib import aclosing
from datetime import UTC, datetime

from fastapi import HTTPException

from ..background_tasks import TaskProgress
from ..db.database import get_async_session
from ..errors import PublicOperationError
from ..minecraft import MCServerStatus, get_docker_mc_manager
from ..operations.context import current_execution, record_phase, revalidate_targets
from ..operations.daemon import run_daemon_mutation
from ..operations.execution import operation_scope, settle_execution
from ..operations.finalization import finalize
from ..operations.journal_types import OperationState, RecoveryReference
from ..servers.port_utils import check_port_conflicts
from ..templates import are_yaml_semantically_equal
from ..world.locks import LockHolder, ServerOperationKind, get_server_operation_lock
from .files import staged_configuration
from .preparation import ServerConfiguration, validate_server_configuration
from .state import (
    ConfigurationConflict,
    ConfigurationState,
    prepared_source_fingerprint,
    read_configuration_state,
    save_configuration_metadata,
)


def check_rebuild_available(server_id: str) -> None:
    if get_server_operation_lock().is_locked(server_id):
        raise HTTPException(status_code=423, detail="服务器正在维护，请等待操作完成")


async def _read(server_id: str) -> ConfigurationState:
    async with get_async_session() as db:
        return await read_configuration_state(db, server_id, get_docker_mc_manager().servers_path)


async def _capture_plan(baseline: ConfigurationState, configuration: ServerConfiguration) -> None:
    execution = current_execution()
    if execution is not None:
        await execution.journal.phase(execution.operation_id, "configuration_prepared", recovery_refs=(
            RecoveryReference("configuration_baseline", baseline.version, resolved=True),
            RecoveryReference("configuration_source", prepared_source_fingerprint(configuration), resolved=True),
        ))


async def _save_source(server_id: str, generation: int, configuration: ServerConfiguration) -> None:
    async with get_async_session() as db:
        await save_configuration_metadata(db, server_id, configuration, generation=generation)
        await db.commit()


async def rebuild_server_task(server_id: str, configuration: ServerConfiguration) -> AsyncGenerator[TaskProgress]:
    holder = LockHolder(ServerOperationKind.REBUILD, datetime.now(UTC), None, "重建服务器")
    async with get_server_operation_lock().try_acquire(server_id, holder, allocate_ports=True) as acquired:
        if not acquired:
            raise HTTPException(status_code=423, detail="服务器正在维护，请等待操作完成")
        try:
            await revalidate_targets()
            async with aclosing(_rebuild_server(server_id, configuration)) as progress:
                async for event in progress:
                    yield event
        except BaseException as failure:
            execution = current_execution()
            if execution is not None:
                if isinstance(failure, ConfigurationConflict):
                    execution.failure_code = failure.code
                state = OperationState.CANCELLED if isinstance(failure, (asyncio.CancelledError, GeneratorExit)) else OperationState.FAILED
                try:
                    await finalize(settle_execution(execution, state))
                except BaseException as settlement_failure:
                    raise failure from settlement_failure
            raise


async def _rebuild_server(server_id: str, configuration: ServerConfiguration) -> AsyncGenerator[TaskProgress]:
    instance = get_docker_mc_manager().get_instance(server_id)
    baseline = await _read(server_id)
    baseline.check_version(configuration.expected_version)
    yield TaskProgress(progress=0, message="验证配置...")
    try:
        game_port, rcon_port = validate_server_configuration(server_id, configuration.yaml_content)
    except Exception as error:
        raise PublicOperationError("无效的 YAML 配置，请检查语法和端口设置") from error
    yield TaskProgress(progress=5, message="检查端口冲突...")
    conflicts = await check_port_conflicts(game_port, rcon_port, exclude_server_id=server_id)
    if conflicts:
        raise PublicOperationError(f"端口冲突: {'; '.join(conflicts)}")

    yield TaskProgress(progress=10, message="获取服务器状态...")
    status = await instance.get_status()
    was_running = status in {MCServerStatus.RUNNING, MCServerStatus.STARTING, MCServerStatus.HEALTHY}
    execution = current_execution()
    if execution is not None:
        await execution.journal.capture_running_intent(execution.operation_id, was_running)
    await _capture_plan(baseline, configuration)

    async with staged_configuration(baseline.compose_path, configuration.yaml_content.encode(), project=instance.get_project_path()) as staged:
        await record_phase("configuration_staged")
        (await _read(server_id)).check_version(baseline.version)
        if was_running or status == MCServerStatus.CREATED:
            yield TaskProgress(progress=15, message="下线服务器...")
            await run_daemon_mutation(instance.down, phase="stopping_server", completed_phase="server_stopped", running_intent=was_running, settle_on_failure=False)
            yield TaskProgress(progress=40, message="服务器已停止")
        else:
            yield TaskProgress(progress=40, message="服务器未运行，跳过停止步骤")

        await revalidate_targets()
        (await _read(server_id)).check_version(baseline.version)
        if await instance.created():
            raise PublicOperationError("服务器容器仍存在，请先下线服务器后重新应用配置")
        yield TaskProgress(progress=45, message="更新配置文件...")
        await record_phase("writing_configuration", changed=True)
        await staged.replace()
        await record_phase("configuration_written", changed=True)
        yield TaskProgress(progress=60, message="配置文件已更新")
        current = await _read(server_id)
        if current.content != configuration.yaml_content.encode() or current.source_version != baseline.source_version:
            raise ConfigurationConflict(current.version)
        yield TaskProgress(progress=62, message="保存配置来源...")
        await record_phase("saving_configuration_source", changed=True)
        await finalize(_save_source(server_id, baseline.server_generation, configuration))
        await record_phase("configuration_source_saved", changed=True)

        if was_running:
            yield TaskProgress(progress=65, message="启动服务器...")
            await run_daemon_mutation(instance.up, phase="starting_server", completed_phase="server_started", running_intent=True, settle_on_failure=False)

    current = await _read(server_id)
    if current.content != configuration.yaml_content.encode() or current.source_version != prepared_source_fingerprint(configuration):
        raise ConfigurationConflict(current.version)
    yield TaskProgress(progress=100, message="配置更新完成", result={
        "game_port": game_port, "rcon_port": rcon_port, "was_running": was_running,
        "version": current.version,
    })


async def convert_without_rebuild(
    server_id: str, configuration: ServerConfiguration | None, *,
    expected_version: str | None = None, actor_id: int | None = None,
) -> bool:
    holder = LockHolder(ServerOperationKind.REBUILD, datetime.now(UTC), actor_id, "转换配置模式")
    async with get_server_operation_lock().try_acquire(server_id, holder) as acquired:
        if not acquired:
            raise HTTPException(status_code=423, detail="服务器正在维护，请等待操作完成")
        baseline = await _read(server_id)
        baseline.check_version(expected_version)
        if configuration is None:
            if baseline.template_id is None:
                raise HTTPException(status_code=400, detail="该服务器已经是直接编辑模式")
            configuration = ServerConfiguration(baseline.yaml_content, expected_version=expected_version)
        elif not are_yaml_semantically_equal(baseline.yaml_content, configuration.yaml_content):
            return False
        async with operation_scope("configuration_apply", [server_id], actor_id=actor_id, name="转换配置模式", configuration_version=ServerConfiguration(baseline.yaml_content).fingerprint):
            await _capture_plan(baseline, configuration)
            await revalidate_targets()
            (await _read(server_id)).check_version(baseline.version)
            await record_phase("saving_configuration_source", changed=True)
            await finalize(_save_source(server_id, baseline.server_generation, configuration))
            await record_phase("configuration_source_saved", changed=True)
        return True
