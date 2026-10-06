"""Application-owned resources and lifecycle composition."""

from __future__ import annotations

import asyncio
import shutil
import tempfile
from collections.abc import (
    AsyncGenerator,
    Awaitable,
    Callable,
    Coroutine,
    Iterator,
)
from contextlib import AsyncExitStack, asynccontextmanager, contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypeVar

from . import runtime_factories
from .runtime_resources import bind_runtime

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

    from .archive.uploads import ArchiveUploadSession
    from .auth.login_code import LoginCodeManager
    from .auth.service import IdentityService
    from .background_tasks.manager import BackgroundTaskManager
    from .chunk_prune.service import ChunkPruneService
    from .config import Settings
    from .cron.manager import CronManager
    from .cron.registry import CronRegistry
    from .cron.restart_scheduler import RestartScheduler
    from .db.database import Database
    from .dns.manager import SimpleDNSManager
    from .dynamic_config import ConfigProxy
    from .dynamic_config.manager import ConfigManager
    from .events.bus import EventBus
    from .files.types import UploadSession
    from .log_monitor.monitor import LogMonitor
    from .mcmap.manager import MCMapManager
    from .minecraft.manager import DockerMCManager
    from .operation_admission import ServerWriteAdmission
    from .operations.coordinator import OperationCoordinator
    from .operations.journal import OperationJournal
    from .operations.recovery import RecoveryService
    from .players.heartbeat import HeartbeatManager
    from .players.player_syncer import PlayerSyncer
    from .players.service import PlayerService
    from .players.skin_fetcher import SkinFetcher
    from .runtime_logging import OwnedLogger
    from .self_check.checks.base import SelfCheckDependencies
    from .self_check.service import SelfCheckService
    from .snapshots.commands import SnapshotCommands
    from .snapshots.previews import SnapshotPreviews
    from .snapshots.service import SnapshotService
    from .world.locks import ServerOperationLock

T = TypeVar("T")


class _Uninitialized:
    pass


UNINITIALIZED = _Uninitialized()


async def _migrate() -> None:
    from .db.migrations import ensure_database_schema

    await ensure_database_schema()


@dataclass(frozen=True)
class RuntimeHooks:
    migrate: Callable[[], Awaitable[None]] = _migrate
    recover: Callable[[Runtime], Awaitable[None]] | None = None


class Runtime:
    def __init__(
        self, settings: Settings | None = None, *,
        hooks: RuntimeHooks | None = None,
    ) -> None:
        if settings is None:
            from .config import Settings

            settings = Settings()  # type: ignore
        self.settings = settings
        self._database: Database | _Uninitialized = UNINITIALIZED
        self._database_engine: AsyncEngine | _Uninitialized = UNINITIALIZED
        self._session_factory: async_sessionmaker[AsyncSession] | _Uninitialized = UNINITIALIZED
        self._config_manager: ConfigManager | _Uninitialized = UNINITIALIZED
        self._dynamic_configuration: ConfigProxy | _Uninitialized = UNINITIALIZED
        self._app_logger: OwnedLogger | _Uninitialized = UNINITIALIZED
        self._audit_logger: OwnedLogger | None | _Uninitialized = UNINITIALIZED
        self._docker_mc_manager: DockerMCManager | _Uninitialized = UNINITIALIZED
        self._snapshot_service: SnapshotService | None | _Uninitialized = UNINITIALIZED
        self._operation_coordinator: OperationCoordinator | _Uninitialized = UNINITIALIZED
        self._server_operation_lock: ServerOperationLock | _Uninitialized = UNINITIALIZED
        self._server_write_admission: ServerWriteAdmission | _Uninitialized = UNINITIALIZED
        self._task_manager: BackgroundTaskManager | _Uninitialized = UNINITIALIZED
        self._snapshot_commands: SnapshotCommands | None | _Uninitialized = UNINITIALIZED
        self._snapshot_previews: SnapshotPreviews | None | _Uninitialized = UNINITIALIZED
        self._chunk_prune_service: ChunkPruneService | _Uninitialized = UNINITIALIZED
        self._mcmap_manager: MCMapManager | _Uninitialized = UNINITIALIZED
        self._event_bus: EventBus | _Uninitialized = UNINITIALIZED
        self._cron_registry: CronRegistry | _Uninitialized = UNINITIALIZED
        self._cron_manager: CronManager | _Uninitialized = UNINITIALIZED
        self._restart_scheduler: RestartScheduler | _Uninitialized = UNINITIALIZED
        self._dns_manager: SimpleDNSManager | _Uninitialized = UNINITIALIZED
        self._login_code_manager: LoginCodeManager | _Uninitialized = UNINITIALIZED
        self._skin_fetcher: SkinFetcher | _Uninitialized = UNINITIALIZED
        self._player_service: PlayerService | _Uninitialized = UNINITIALIZED
        self._heartbeat_manager: HeartbeatManager | _Uninitialized = UNINITIALIZED
        self._player_syncer: PlayerSyncer | _Uninitialized = UNINITIALIZED
        self._log_monitor: LogMonitor | _Uninitialized = UNINITIALIZED
        self._identity_service: IdentityService | _Uninitialized = UNINITIALIZED
        self._self_check_dependencies: SelfCheckDependencies | _Uninitialized = UNINITIALIZED
        self._self_check_service: SelfCheckService | _Uninitialized = UNINITIALIZED
        self._archive_upload_sessions: dict[str, ArchiveUploadSession] | _Uninitialized = UNINITIALIZED
        self._file_upload_sessions: dict[str, UploadSession] | _Uninitialized = UNINITIALIZED
        self._archive_upload_lock: asyncio.Lock | _Uninitialized = UNINITIALIZED
        self._server_sync_lock: asyncio.Lock | _Uninitialized = UNINITIALIZED
        self.operation_recovery: RecoveryService | None = None
        self.world_restore_stages: set[str] = set()
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

    @property
    def database(self) -> Database:
        if isinstance(self._database, _Uninitialized):
            with self.bind():
                self._database = runtime_factories.create_database(self)
        return self._database

    @property
    def database_engine(self) -> AsyncEngine:
        if isinstance(self._database_engine, _Uninitialized):
            with self.bind():
                self._database_engine = runtime_factories.create_database_engine(self)
        return self._database_engine

    @property
    def session_factory(self) -> async_sessionmaker[AsyncSession]:
        if isinstance(self._session_factory, _Uninitialized):
            with self.bind():
                self._session_factory = runtime_factories.create_session_factory(self)
        return self._session_factory

    @property
    def config_manager(self) -> ConfigManager:
        if isinstance(self._config_manager, _Uninitialized):
            with self.bind():
                self._config_manager = runtime_factories.create_config_manager(self)
        return self._config_manager

    @property
    def dynamic_configuration(self) -> ConfigProxy:
        if isinstance(self._dynamic_configuration, _Uninitialized):
            with self.bind():
                self._dynamic_configuration = runtime_factories.create_dynamic_configuration(self)
        return self._dynamic_configuration

    @property
    def app_logger(self) -> OwnedLogger:
        if isinstance(self._app_logger, _Uninitialized):
            with self.bind():
                self._app_logger = runtime_factories.create_app_logger(self)
        return self._app_logger

    @property
    def audit_logger(self) -> OwnedLogger | None:
        if isinstance(self._audit_logger, _Uninitialized):
            with self.bind():
                self._audit_logger = runtime_factories.create_audit_logger(self)
        return self._audit_logger

    @property
    def docker_mc_manager(self) -> DockerMCManager:
        if isinstance(self._docker_mc_manager, _Uninitialized):
            with self.bind():
                self._docker_mc_manager = runtime_factories.create_docker_mc_manager(self)
        return self._docker_mc_manager

    @property
    def snapshot_service(self) -> SnapshotService | None:
        if isinstance(self._snapshot_service, _Uninitialized):
            with self.bind():
                self._snapshot_service = runtime_factories.create_snapshot_service(self)
        return self._snapshot_service

    @property
    def operation_coordinator(self) -> OperationCoordinator:
        if isinstance(self._operation_coordinator, _Uninitialized):
            with self.bind():
                self._operation_coordinator = runtime_factories.create_operation_coordinator(self)
        return self._operation_coordinator

    @property
    def server_operation_lock(self) -> ServerOperationLock:
        if isinstance(self._server_operation_lock, _Uninitialized):
            with self.bind():
                self._server_operation_lock = runtime_factories.create_server_operation_lock(self)
        return self._server_operation_lock

    @property
    def server_write_admission(self) -> ServerWriteAdmission:
        if isinstance(self._server_write_admission, _Uninitialized):
            with self.bind():
                self._server_write_admission = runtime_factories.create_server_write_admission(self)
        return self._server_write_admission

    @property
    def task_manager(self) -> BackgroundTaskManager:
        if isinstance(self._task_manager, _Uninitialized):
            with self.bind():
                self._task_manager = runtime_factories.create_task_manager(self)
        return self._task_manager

    @property
    def snapshot_commands(self) -> SnapshotCommands | None:
        if isinstance(self._snapshot_commands, _Uninitialized):
            with self.bind():
                self._snapshot_commands = runtime_factories.create_snapshot_commands(self)
        return self._snapshot_commands

    @property
    def snapshot_previews(self) -> SnapshotPreviews | None:
        if isinstance(self._snapshot_previews, _Uninitialized):
            with self.bind():
                self._snapshot_previews = runtime_factories.create_snapshot_previews(self)
        return self._snapshot_previews

    @property
    def chunk_prune_service(self) -> ChunkPruneService:
        if isinstance(self._chunk_prune_service, _Uninitialized):
            with self.bind():
                self._chunk_prune_service = runtime_factories.create_chunk_prune_service(self)
        return self._chunk_prune_service

    @property
    def mcmap_manager(self) -> MCMapManager:
        if isinstance(self._mcmap_manager, _Uninitialized):
            with self.bind():
                self._mcmap_manager = runtime_factories.create_mcmap_manager(self)
        return self._mcmap_manager

    @property
    def event_bus(self) -> EventBus:
        if isinstance(self._event_bus, _Uninitialized):
            with self.bind():
                self._event_bus = runtime_factories.create_event_bus(self)
        return self._event_bus

    @property
    def cron_registry(self) -> CronRegistry:
        if isinstance(self._cron_registry, _Uninitialized):
            with self.bind():
                self._cron_registry = runtime_factories.create_cron_registry(self)
        return self._cron_registry

    @property
    def cron_manager(self) -> CronManager:
        if isinstance(self._cron_manager, _Uninitialized):
            with self.bind():
                self._cron_manager = runtime_factories.create_cron_manager(self)
        return self._cron_manager

    @property
    def restart_scheduler(self) -> RestartScheduler:
        if isinstance(self._restart_scheduler, _Uninitialized):
            with self.bind():
                self._restart_scheduler = runtime_factories.create_restart_scheduler(self)
        return self._restart_scheduler

    @property
    def dns_manager(self) -> SimpleDNSManager:
        if isinstance(self._dns_manager, _Uninitialized):
            with self.bind():
                self._dns_manager = runtime_factories.create_dns_manager(self)
        return self._dns_manager

    @property
    def login_code_manager(self) -> LoginCodeManager:
        if isinstance(self._login_code_manager, _Uninitialized):
            with self.bind():
                self._login_code_manager = runtime_factories.create_login_code_manager(self)
        return self._login_code_manager

    @property
    def skin_fetcher(self) -> SkinFetcher:
        if isinstance(self._skin_fetcher, _Uninitialized):
            with self.bind():
                self._skin_fetcher = runtime_factories.create_skin_fetcher(self)
        return self._skin_fetcher

    @property
    def player_service(self) -> PlayerService:
        if isinstance(self._player_service, _Uninitialized):
            with self.bind():
                self._player_service = runtime_factories.create_player_service(self)
        return self._player_service

    @property
    def heartbeat_manager(self) -> HeartbeatManager:
        if isinstance(self._heartbeat_manager, _Uninitialized):
            with self.bind():
                self._heartbeat_manager = runtime_factories.create_heartbeat_manager(self)
        return self._heartbeat_manager

    @property
    def player_syncer(self) -> PlayerSyncer:
        if isinstance(self._player_syncer, _Uninitialized):
            with self.bind():
                self._player_syncer = runtime_factories.create_player_syncer(self)
        return self._player_syncer

    @property
    def log_monitor(self) -> LogMonitor:
        if isinstance(self._log_monitor, _Uninitialized):
            with self.bind():
                self._log_monitor = runtime_factories.create_log_monitor(self)
        return self._log_monitor

    @property
    def identity_service(self) -> IdentityService:
        if isinstance(self._identity_service, _Uninitialized):
            with self.bind():
                self._identity_service = runtime_factories.create_identity_service(self)
        return self._identity_service

    @property
    def self_check_dependencies(self) -> SelfCheckDependencies:
        if isinstance(self._self_check_dependencies, _Uninitialized):
            with self.bind():
                self._self_check_dependencies = runtime_factories.create_self_check_dependencies(self)
        return self._self_check_dependencies

    @property
    def self_check_service(self) -> SelfCheckService:
        if isinstance(self._self_check_service, _Uninitialized):
            with self.bind():
                self._self_check_service = runtime_factories.create_self_check_service(self)
        return self._self_check_service

    @property
    def archive_upload_sessions(self) -> dict[str, ArchiveUploadSession]:
        if isinstance(self._archive_upload_sessions, _Uninitialized):
            with self.bind():
                self._archive_upload_sessions = {}
        return self._archive_upload_sessions

    @property
    def file_upload_sessions(self) -> dict[str, UploadSession]:
        if isinstance(self._file_upload_sessions, _Uninitialized):
            with self.bind():
                self._file_upload_sessions = {}
        return self._file_upload_sessions

    @property
    def archive_upload_lock(self) -> asyncio.Lock:
        if isinstance(self._archive_upload_lock, _Uninitialized):
            with self.bind():
                self._archive_upload_lock = asyncio.Lock()
        return self._archive_upload_lock

    @property
    def server_sync_lock(self) -> asyncio.Lock:
        if isinstance(self._server_sync_lock, _Uninitialized):
            with self.bind():
                self._server_sync_lock = asyncio.Lock()
        return self._server_sync_lock

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
            from .snapshots.previews import get_snapshot_previews

            get_server_write_admission().close()
            try:
                await self._cleanup.enter_async_context(SingleWriterGuard(
                    self.settings.database_url, self.settings.server_path,
                ))
                _ = self.database
                await self.hooks.migrate()
                await get_config_manager().initialize_all_configs()
                await self._recover()

                previews = get_snapshot_previews()
                await self.chunk_prune_service.start()
                if previews is not None:
                    await previews.prepare()

                try:
                    await get_dns_manager().initialize()
                    async with get_async_session() as db:
                        await get_dns_manager().update(db)
                except Exception as exc:  # noqa: BLE001 - optional connectivity cannot prevent local administration
                    from .errors import log_safe_error

                    log_safe_error(exc, "Optional connectivity reconciliation failed")
                await start_player_system()
                await get_cron_manager().initialize()
                if previews is not None:
                    previews.start_janitor()
                get_server_write_admission().open()
                self.started = True
            except BaseException:
                await self.close()
                raise

    async def _close_app_logger(self) -> None:
        resource = self._app_logger
        if isinstance(resource, _Uninitialized) or resource is None:
            return
        resource.close()

    async def _close_audit_logger(self) -> None:
        resource = self._audit_logger
        if isinstance(resource, _Uninitialized) or resource is None:
            return
        resource.close()

    async def _close_database(self) -> None:
        resource = self._database
        if isinstance(resource, _Uninitialized) or resource is None:
            return
        await resource.close()

    async def _close_event_bus(self) -> None:
        resource = self._event_bus
        if isinstance(resource, _Uninitialized) or resource is None:
            return
        resource.close()

    async def _close_login_code_manager(self) -> None:
        resource = self._login_code_manager
        if isinstance(resource, _Uninitialized) or resource is None:
            return
        await resource.close()

    async def _close_dns_manager(self) -> None:
        resource = self._dns_manager
        if isinstance(resource, _Uninitialized) or resource is None:
            return
        await resource.close()

    async def _close_mcmap_manager(self) -> None:
        resource = self._mcmap_manager
        if isinstance(resource, _Uninitialized) or resource is None:
            return
        try:
            await resource.close()
        except BaseException:
            self._scratch_cleanup_safe = False
            raise

    async def _close_snapshot_previews(self) -> None:
        resource = self._snapshot_previews
        if isinstance(resource, _Uninitialized) or resource is None:
            return
        try:
            await resource.close(preserve_artifacts=not self._temporary_cleanup_safe)
        except BaseException:
            self._scratch_cleanup_safe = False
            raise

    async def _close_chunk_prune_service(self) -> None:
        resource = self._chunk_prune_service
        if isinstance(resource, _Uninitialized) or resource is None:
            return
        await resource.close(preserve_artifacts=not self._temporary_cleanup_safe)

    async def _close_task_manager(self) -> None:
        resource = self._task_manager
        if isinstance(resource, _Uninitialized) or resource is None:
            return
        try:
            await resource.shutdown()
        except BaseException:
            self._temporary_cleanup_safe = self._scratch_cleanup_safe = False
            raise

    async def _close_heartbeat_manager(self) -> None:
        resource = self._heartbeat_manager
        if isinstance(resource, _Uninitialized) or resource is None:
            return
        await resource.stop()

    async def _close_log_monitor(self) -> None:
        resource = self._log_monitor
        if isinstance(resource, _Uninitialized) or resource is None:
            return
        await resource.stop_all()

    async def _close_player_syncer(self) -> None:
        resource = self._player_syncer
        if isinstance(resource, _Uninitialized) or resource is None:
            return
        await resource.stop()

    async def _close_cron_manager(self) -> None:
        resource = self._cron_manager
        if isinstance(resource, _Uninitialized) or resource is None:
            return
        await resource.shutdown()

    async def _close_uploads(self) -> None:
        if not self._temporary_cleanup_safe:
            return
        if not isinstance(self._archive_upload_sessions, _Uninitialized):
            from .archive.uploads import close_archive_uploads

            await close_archive_uploads()
        sessions = self._file_upload_sessions
        if not isinstance(sessions, _Uninitialized):
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
            admission = self._server_write_admission
            if not isinstance(admission, _Uninitialized):
                admission.close()
            try:
                async with AsyncExitStack() as shutdown:
                    shutdown.push_async_callback(self._cleanup.aclose)
                    shutdown.push_async_callback(self._close_scratch)
                    shutdown.push_async_callback(self._close_app_logger)
                    shutdown.push_async_callback(self._close_audit_logger)
                    shutdown.push_async_callback(self._close_database)
                    shutdown.push_async_callback(self._close_event_bus)
                    shutdown.push_async_callback(self._close_login_code_manager)
                    shutdown.push_async_callback(self._close_dns_manager)
                    shutdown.push_async_callback(self._close_mcmap_manager)
                    shutdown.push_async_callback(self._close_snapshot_previews)
                    shutdown.push_async_callback(self._close_chunk_prune_service)
                    shutdown.push_async_callback(self._close_uploads)
                    shutdown.push_async_callback(self._verify_writers_stopped)
                    shutdown.push_async_callback(self._close_task_manager)
                    shutdown.push_async_callback(self._stop_tasks, self._background)
                    shutdown.push_async_callback(self._stop_tasks, self.requests)
                    shutdown.push_async_callback(self._close_heartbeat_manager)
                    shutdown.push_async_callback(self._close_log_monitor)
                    shutdown.push_async_callback(self._close_player_syncer)
                    shutdown.push_async_callback(self._close_cron_manager)
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
