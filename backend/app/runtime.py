"""Application-owned resources and lifecycle composition."""

import asyncio
import inspect
import shutil
import tempfile
from collections.abc import (
    AsyncGenerator,
    Awaitable,
    Callable,
    Coroutine,
    Iterator,
    Mapping,
)
from contextlib import AsyncExitStack, asynccontextmanager, contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypeVar

from .runtime_factories import create_resource
from .runtime_resources import bind_runtime

if TYPE_CHECKING:
    from .config import Settings
    from .db.database import Database
    from .operations.journal import OperationJournal

T = TypeVar("T")


async def _migrate() -> None:
    from .db.migrations import ensure_database_schema

    await ensure_database_schema()


@dataclass(frozen=True)
class RuntimeHooks:
    migrate: Callable[[], Awaitable[None]] = _migrate
    recover: Callable[["Runtime"], Awaitable[None]] | None = None


class Runtime:
    def __init__(
        self, settings: "Settings | None" = None, *,
        overrides: Mapping[str, Any] | None = None,
        hooks: RuntimeHooks | None = None,
    ) -> None:
        if settings is None:
            from .config import Settings

            settings = Settings()  # type: ignore
        self.settings = settings
        self.resources: dict[str, Any] = {"settings": settings, **(overrides or {})}
        self.hooks = hooks or RuntimeHooks()
        self.journal: OperationJournal | None = None
        self._scratch: Path | None = None
        self._scratch_cleanup_safe = True
        self._temporary_cleanup_safe = True
        self._background: set[asyncio.Task] = set()
        self.requests: set[asyncio.Task] = set()
        self._cleanup = AsyncExitStack()
        self._close_task: asyncio.Task[None] | None = None
        self.started = False
        self.closing = False
        self.closed = False

    @contextmanager
    def bind(self) -> Iterator[None]:
        with bind_runtime(self):
            yield

    def resource(self, name: str) -> Any:
        if name not in self.resources:
            with self.bind():
                self.resources[name] = create_resource(self, name)
        return self.resources[name]

    @property
    def database(self) -> "Database":
        return self.resource("database")

    @property
    def scratch_dir(self) -> Path:
        if self._scratch is None:
            self._scratch = Path(tempfile.mkdtemp(prefix="mc-admin-runtime-"))
        return self._scratch

    def spawn(self, coroutine: Coroutine[Any, Any, T], *, name: str) -> asyncio.Task[T]:
        from .operations.context import bind_execution

        if self.closing or self.closed:
            coroutine.close()
            raise RuntimeError("应用正在关闭，不能启动后台工作")
        with self.bind(), bind_execution(None):
            task = asyncio.create_task(coroutine, name=name)
        self._background.add(task)
        task.add_done_callback(self._background.discard)
        return task

    async def _stop_tasks(self, tasks: set[asyncio.Task]) -> None:
        current = asyncio.current_task()
        pending = [task for task in tasks if task is not current and not task.done()]
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)

    async def _recover(self) -> None:
        if self.hooks.recover is not None:
            await self.hooks.recover(self)
            return
        from .operations.execution import recover_runtime

        await recover_runtime(self)

    async def start(self) -> None:
        from .operations.context import bind_execution

        if self.started:
            return
        if self.closed:
            raise RuntimeError("已关闭的运行时不能重新启动，请创建新的运行时")
        with self.bind(), bind_execution(None):
            from .cron import get_cron_manager
            from .db.database import get_async_session
            from .dns import get_dns_manager
            from .dynamic_config import get_config_manager
            from .operation_admission import get_server_write_admission
            from .operations.single_writer import SingleWriterGuard
            from .players import start_player_system
            from .world import get_world_restore_orchestrator

            get_server_write_admission().close()
            try:
                await self._cleanup.enter_async_context(SingleWriterGuard(
                    self.settings.database_url, self.settings.server_path,
                ))
                self.resource("database")
                await self.hooks.migrate()
                await get_config_manager().initialize_all_configs()
                await self._recover()

                orchestrator = get_world_restore_orchestrator()
                await self.resource("chunk_prune_service").start()
                if orchestrator is not None:
                    await orchestrator.prepare()

                try:
                    await get_dns_manager().initialize()
                    async with get_async_session() as db:
                        await get_dns_manager().update(db)
                except Exception as exc:  # noqa: BLE001 - optional connectivity cannot prevent local administration
                    from .errors import log_safe_error

                    log_safe_error(exc, "Optional connectivity reconciliation failed")
                await start_player_system()
                await get_cron_manager().initialize()
                if orchestrator is not None:
                    orchestrator.start_janitor()
                get_server_write_admission().open()
                self.started = True
            except BaseException:
                await self.close()
                raise

    async def _close_resource(self, name: str, method: str) -> None:
        resource = self.resources.get(name)
        if resource is not None:
            try:
                closer = getattr(resource, method)
                result = (
                    closer(preserve_artifacts=True)
                    if name in {"world_restore_orchestrator", "chunk_prune_service"} and not self._temporary_cleanup_safe
                    else closer()
                )
                if inspect.isawaitable(result):
                    await result
            except BaseException:
                if name in {"mcmap_manager", "world_restore_orchestrator"}:
                    self._scratch_cleanup_safe = False
                if name == "task_manager":
                    self._temporary_cleanup_safe = self._scratch_cleanup_safe = False
                raise

    async def _close_uploads(self) -> None:
        if not self._temporary_cleanup_safe:
            return
        if "archive_upload_sessions" in self.resources:
            from .archive.uploads import close_archive_uploads

            await close_archive_uploads()
        sessions = self.resources.get("file_upload_sessions")
        if sessions is not None:
            sessions.clear()

    async def _close_scratch(self) -> None:
        if self._scratch is not None and self._scratch_cleanup_safe:
            await asyncio.to_thread(shutil.rmtree, self._scratch)
            self._scratch = None

    async def _verify_writers_stopped(self) -> None:
        if self.journal is None:
            return
        try:
            records = await self.journal.unsettled()
        except Exception as error:
            self._temporary_cleanup_safe = self._scratch_cleanup_safe = False
            raise RuntimeError("无法验证操作日志中的写入终态；已保留临时产物，请检查操作历史") from error
        unconfirmed = [
            record for record in records
            if not record.writers_stopped or not record.ownership_known or record.processes
        ]
        if unconfirmed:
            self._temporary_cleanup_safe = self._scratch_cleanup_safe = False
            identifiers = ", ".join(record.operation_id for record in unconfirmed[:10])
            raise RuntimeError(
                f"{len(unconfirmed)} 个操作的写入尚未确认结束；已保留临时产物，请检查操作历史：{identifiers}"
            )

    async def close(self) -> None:
        if self.closed:
            return
        from .operations.context import bind_execution
        from .operations.finalization import finalize

        if self._close_task is None:
            self.closing = True
            with self.bind(), bind_execution(None):
                self._close_task = asyncio.create_task(self._close(), name="runtime-close")
        await finalize(self._close_task)

    async def _close(self) -> None:
        self.closing = True
        with self.bind():
            admission = self.resources.get("server_write_admission")
            if admission is not None:
                admission.close()
            try:
                async with AsyncExitStack() as shutdown:
                    shutdown.push_async_callback(self._cleanup.aclose)
                    shutdown.push_async_callback(self._close_scratch)
                    for name, method in (
                        ("app_logger", "close"), ("audit_logger", "close"),
                        ("database", "close"), ("event_bus", "close"),
                        ("login_code_manager", "close"), ("dns_manager", "close"),
                        ("mcmap_manager", "close"), ("world_restore_orchestrator", "close"),
                        ("chunk_prune_service", "close"),
                    ):
                        shutdown.push_async_callback(self._close_resource, name, method)
                    shutdown.push_async_callback(self._close_uploads)
                    shutdown.push_async_callback(self._verify_writers_stopped)
                    shutdown.push_async_callback(self._close_resource, "task_manager", "shutdown")
                    shutdown.push_async_callback(self._stop_tasks, self._background)
                    shutdown.push_async_callback(self._stop_tasks, self.requests)
                    for name, method in (
                        ("heartbeat_manager", "stop"), ("log_monitor", "stop_all"),
                        ("player_syncer", "stop"), ("cron_manager", "shutdown"),
                    ):
                        shutdown.push_async_callback(self._close_resource, name, method)
            finally:
                self.closed = True

    @asynccontextmanager
    async def lifespan(self) -> AsyncGenerator[None]:
        with self.bind():
            await self.start()
            try:
                yield
            finally:
                await self.close()
