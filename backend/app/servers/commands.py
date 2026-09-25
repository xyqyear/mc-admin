"""Public lifecycle commands shared by HTTP and scheduled triggers."""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from fastapi import HTTPException

from ..config import get_settings
from ..db.database import get_async_session
from ..minecraft import get_docker_mc_manager
from ..operations.daemon import run_daemon_mutation
from ..operations.execution import operation_scope
from ..world.locks import LockHolder, ServerOperationKind, get_server_operation_lock
from .references import ServerRef, resolve_server_ref, revalidate_server_ref

ServerAction = Literal["start", "up", "restart", "stop", "down"]


@dataclass(frozen=True)
class ServerCommandResult:
    skipped: bool = False
    reason: str | None = None


class ServerCommands:
    async def execute(
        self,
        server_id: str,
        action: ServerAction,
        *,
        actor_id: int | None = None,
        only_if_running: bool = False,
        expected_generation: int | None = None,
    ) -> ServerCommandResult:
        settings = get_settings()
        if only_if_running and action != "restart":
            raise ValueError("仅定时重启支持跳过已停止服务器")
        try:
            async with get_async_session() as session:
                reference = await resolve_server_ref(session, server_id, servers_root=settings.server_path)
        except HTTPException as exc:
            if only_if_running and expected_generation is not None and exc.status_code in (404, 409):
                return ServerCommandResult(True, "计划绑定的服务器实例已停用，跳过同名新实例的重启")
            raise
        if expected_generation is not None and reference.generation != expected_generation:
            return ServerCommandResult(True, "计划绑定的服务器实例已停用，跳过同名新实例的重启")
        if action in ("stop", "down"):
            await self._run(reference, action, actor_id)
            return ServerCommandResult()

        holder = LockHolder(ServerOperationKind.START, datetime.now(UTC), actor_id, "定时重启服务器" if only_if_running else "启动服务器")
        async with get_server_operation_lock().try_acquire(server_id, holder) as acquired:
            if not acquired:
                if only_if_running:
                    return ServerCommandResult(True, "服务器正在维护，跳过重启")
                raise HTTPException(status_code=423, detail="服务器正在维护，请等待操作完成")
            async with get_async_session() as session:
                try:
                    await revalidate_server_ref(session, reference)
                except HTTPException as exc:
                    if only_if_running and expected_generation is not None and exc.status_code in (404, 409):
                        return ServerCommandResult(True, "计划绑定的服务器实例已停用，跳过同名新实例的重启")
                    raise
            instance = get_docker_mc_manager().get_instance(server_id)
            if not await instance.exists():
                raise HTTPException(status_code=404, detail=f"Server '{server_id}' not found")
            if only_if_running and not await instance.running():
                return ServerCommandResult(True, f"服务器 '{server_id}' 未在运行中，跳过重启")
            await self._run(reference, action, actor_id)
        return ServerCommandResult()

    async def _run(self, reference: ServerRef, action: ServerAction, actor_id: int | None) -> None:
        async with get_async_session() as session:
            await revalidate_server_ref(session, reference)
        instance = get_docker_mc_manager().get_instance(reference.server_id)
        phases = {
            "start": ("starting_server", "server_started", True),
            "up": ("starting_server", "server_started", True),
            "restart": ("restarting_server", "server_restarted", True),
            "stop": ("stopping_server", "server_stopped", False),
            "down": ("removing_container", "server_down", False),
        }
        phase, completed_phase, running_intent = phases[action]
        async with operation_scope(f"server_{action}", [reference.server_id], actor_id=actor_id):
            await run_daemon_mutation(
                getattr(instance, action), phase=phase, completed_phase=completed_phase,
                running_intent=running_intent,
            )
