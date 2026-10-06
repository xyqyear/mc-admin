"""Explicit construction of resources owned by one application runtime."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

    from .auth.login_code import LoginCodeManager
    from .auth.service import IdentityService
    from .background_tasks.manager import BackgroundTaskManager
    from .chunk_prune.service import ChunkPruneService
    from .cron.manager import CronManager
    from .cron.registry import CronRegistry
    from .cron.restart_scheduler import RestartScheduler
    from .db.database import Database
    from .dns.manager import SimpleDNSManager
    from .dynamic_config import ConfigProxy
    from .dynamic_config.manager import ConfigManager
    from .events.bus import EventBus
    from .log_monitor.monitor import LogMonitor
    from .mcmap.manager import MCMapManager
    from .minecraft.manager import DockerMCManager
    from .operation_admission import ServerWriteAdmission
    from .operations.coordinator import OperationCoordinator
    from .players.heartbeat import HeartbeatManager
    from .players.player_syncer import PlayerSyncer
    from .players.service import PlayerService
    from .players.skin_fetcher import SkinFetcher
    from .runtime import Runtime
    from .runtime_logging import OwnedLogger
    from .self_check.checks.base import SelfCheckDependencies
    from .self_check.service import SelfCheckService
    from .snapshots.commands import SnapshotCommands
    from .snapshots.previews import SnapshotPreviews
    from .snapshots.service import SnapshotService
    from .world.locks import ServerOperationLock


def create_database(runtime: Runtime) -> Database:
    from .db.database import Database

    return Database(runtime.settings.database_url)


def create_database_engine(runtime: Runtime) -> AsyncEngine:
    return runtime.database.engine


def create_session_factory(runtime: Runtime) -> async_sessionmaker[AsyncSession]:
    return runtime.database.session_factory


def create_config_manager(runtime: Runtime) -> ConfigManager:
    from .dynamic_config.manager import create_config_manager

    return create_config_manager(
        session_factory=runtime.database.session_factory
    )


def create_dynamic_configuration(runtime: Runtime) -> ConfigProxy:
    from .dynamic_config import ConfigProxy

    return ConfigProxy(runtime.config_manager)


def create_app_logger(runtime: Runtime) -> OwnedLogger:
    from .logger import create_logger

    return create_logger()


def create_audit_logger(runtime: Runtime) -> OwnedLogger | None:
    from .audit import create_audit_logger

    return create_audit_logger()


def create_docker_mc_manager(runtime: Runtime) -> DockerMCManager:
    from .minecraft.manager import DockerMCManager

    return DockerMCManager(runtime.settings.server_path)


def create_snapshot_service(runtime: Runtime) -> SnapshotService | None:
    from .snapshots.restic import ResticClient
    from .snapshots.service import SnapshotService

    restic = runtime.settings.restic
    if restic is None:
        return None
    return SnapshotService(
        ResticClient(
            repository_path=restic.repository_path,
            password=restic.password,
            binary_path=runtime.settings.restic_binary_path,
        ),
        runtime.docker_mc_manager,
    )


def create_operation_coordinator(runtime: Runtime) -> OperationCoordinator:
    from .operations.coordinator import OperationCoordinator

    return OperationCoordinator()


def create_server_operation_lock(runtime: Runtime) -> ServerOperationLock:
    from .world.locks import ServerOperationLock

    return ServerOperationLock(runtime.operation_coordinator)


def create_server_write_admission(runtime: Runtime) -> ServerWriteAdmission:
    from .operation_admission import ServerWriteAdmission

    return ServerWriteAdmission()


def create_task_manager(runtime: Runtime) -> BackgroundTaskManager:
    from .background_tasks.manager import BackgroundTaskManager

    return BackgroundTaskManager(runtime.journal)


def create_snapshot_commands(runtime: Runtime) -> SnapshotCommands | None:
    from .snapshots.commands import SnapshotCommands

    snapshots = runtime.snapshot_service
    if snapshots is None:
        return None
    return SnapshotCommands(
        snapshots,
        runtime.docker_mc_manager,
        runtime.server_operation_lock,
        runtime.task_manager,
        runtime.database.session_factory,
        runtime.settings.server_path,
        runtime.snapshot_previews,
    )


def create_snapshot_previews(runtime: Runtime) -> SnapshotPreviews | None:
    from .snapshots.previews import SnapshotPreviews

    snapshots = runtime.snapshot_service
    if snapshots is None:
        return None
    return SnapshotPreviews(
        snapshots,
        runtime.docker_mc_manager,
        runtime.server_operation_lock,
        runtime.task_manager,
        runtime.database.session_factory,
        runtime.settings.server_path,
    )


def create_chunk_prune_service(runtime: Runtime) -> ChunkPruneService:
    from .chunk_prune.service import ChunkPruneService

    return ChunkPruneService(
        docker=runtime.docker_mc_manager,
        operation_lock=runtime.server_operation_lock,
    )


def create_mcmap_manager(runtime: Runtime) -> MCMapManager:
    from .mcmap.manager import MCMapManager

    return MCMapManager()


def create_event_bus(runtime: Runtime) -> EventBus:
    from .events.bus import EventBus

    return EventBus()


def create_cron_registry(runtime: Runtime) -> CronRegistry:
    from .cron.registry import create_cron_registry

    return create_cron_registry()


def create_cron_manager(runtime: Runtime) -> CronManager:
    from .cron.manager import CronManager

    return CronManager()


def create_restart_scheduler(runtime: Runtime) -> RestartScheduler:
    from .cron.restart_scheduler import RestartScheduler

    return RestartScheduler(runtime.cron_manager)


def create_dns_manager(runtime: Runtime) -> SimpleDNSManager:
    from .dns.manager import SimpleDNSManager

    configuration = runtime.dynamic_configuration
    return SimpleDNSManager(
        configuration=lambda: configuration.dns,
        docker_manager=runtime.docker_mc_manager,
    )


def create_login_code_manager(runtime: Runtime) -> LoginCodeManager:
    from .auth.login_code import LoginCodeManager

    return LoginCodeManager()


def create_skin_fetcher(runtime: Runtime) -> SkinFetcher:
    from .players.skin_fetcher import SkinFetcher

    return SkinFetcher()


def create_player_service(runtime: Runtime) -> PlayerService:
    from .players.identity_resolver import resolve_player_by_name
    from .players.name_filters import is_ignored_player_name
    from .players.service import PlayerService

    async def resolve_name(server_id: str, player_name: str):
        with runtime.bind():
            return await resolve_player_by_name(server_id, player_name)

    def ignored_name(player_name: str) -> bool:
        with runtime.bind():
            return is_ignored_player_name(player_name)

    return PlayerService(
        session_factory=runtime.database.session_factory,
        publish=runtime.event_bus.publish,
        spawn=lambda coroutine: runtime.spawn(
            coroutine, name="player-skin-update"
        ),
        skin_client=runtime.skin_fetcher,
        resolve_name=resolve_name,
        ignored_name=ignored_name,
    )


def create_heartbeat_manager(runtime: Runtime) -> HeartbeatManager:
    from .players.heartbeat import HeartbeatManager

    return HeartbeatManager(runtime.player_service)


def create_player_syncer(runtime: Runtime) -> PlayerSyncer:
    from .players.player_syncer import PlayerSyncer

    return PlayerSyncer(runtime.player_service)


def create_log_monitor(runtime: Runtime) -> LogMonitor:
    from .log_monitor.monitor import LogMonitor

    return LogMonitor(runtime.player_service)


def create_identity_service(runtime: Runtime) -> IdentityService:
    from .auth.service import IdentityService

    return IdentityService(
        settings=runtime.settings,
        session_factory=runtime.database.session_factory,
    )


def create_self_check_dependencies(runtime: Runtime) -> SelfCheckDependencies:
    from .self_check.checks.base import SelfCheckDependencies

    return SelfCheckDependencies(
        settings=runtime.settings,
        configuration=runtime.dynamic_configuration,
        minecraft=runtime.docker_mc_manager,
        snapshots=runtime.snapshot_service,
        connectivity=runtime.dns_manager,
        logs=runtime.log_monitor,
        locks=runtime.server_operation_lock,
    )


def create_self_check_service(runtime: Runtime) -> SelfCheckService:
    from .self_check.service import SelfCheckService

    return SelfCheckService(
        session_factory=runtime.database.session_factory,
        dependencies=runtime.self_check_dependencies,
    )
