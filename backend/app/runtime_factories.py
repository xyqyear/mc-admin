"""Explicit construction of resources owned by one application runtime."""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .runtime import Runtime


def create_resource(runtime: "Runtime", name: str) -> Any:
    match name:
        case "database":
            from .db.database import Database
            return Database(runtime.settings.database_url)
        case "database_engine":
            return runtime.database.engine
        case "session_factory":
            return runtime.database.session_factory
        case "config_manager":
            from .dynamic_config.manager import create_config_manager
            return create_config_manager(session_factory=runtime.database.session_factory)
        case "dynamic_configuration":
            from .dynamic_config import ConfigProxy
            return ConfigProxy(runtime.resource("config_manager"))
        case "app_logger":
            from .logger import create_logger
            return create_logger()
        case "audit_logger":
            from .audit import create_audit_logger
            return create_audit_logger()
        case "docker_mc_manager":
            from .minecraft.manager import DockerMCManager
            return DockerMCManager(runtime.settings.server_path)
        case "snapshot_service":
            from .snapshots.restic import ResticClient
            from .snapshots.service import SnapshotService
            restic = runtime.settings.restic
            if restic is None:
                return None
            return SnapshotService(ResticClient(
                repository_path=restic.repository_path,
                password=restic.password,
                binary_path=runtime.settings.restic_binary_path,
            ), runtime.resource("docker_mc_manager"))
        case "operation_coordinator":
            from .operations.coordinator import OperationCoordinator
            return OperationCoordinator()
        case "server_operation_lock":
            from .world.locks import ServerOperationLock
            return ServerOperationLock(runtime.resource("operation_coordinator"))
        case "server_write_admission":
            from .operation_admission import ServerWriteAdmission
            return ServerWriteAdmission()
        case "task_manager":
            from .background_tasks.manager import BackgroundTaskManager
            return BackgroundTaskManager(runtime.journal)
        case "world_restore_orchestrator":
            from .world.artifacts import artifact_root
            from .world.restore import WorldRestoreOrchestrator
            snapshots = runtime.resource("snapshot_service")
            if snapshots is None:
                return None
            return WorldRestoreOrchestrator(
                snapshot_service=snapshots,
                docker_mc_manager=runtime.resource("docker_mc_manager"),
                server_operation_lock=runtime.resource("server_operation_lock"),
                session_factory=runtime.database.session_factory,
                preview_base_dir=artifact_root("restore"),
                servers_root=runtime.settings.server_path,
            )
        case "chunk_prune_service":
            from .chunk_prune.service import ChunkPruneService
            return ChunkPruneService(
                docker=runtime.resource("docker_mc_manager"),
                operation_lock=runtime.resource("server_operation_lock"),
            )
        case "mcmap_manager":
            from .mcmap.manager import MCMapManager
            return MCMapManager()
        case "event_bus":
            from .events.bus import EventBus
            return EventBus()
        case "cron_registry":
            from .cron.registry import create_cron_registry
            return create_cron_registry()
        case "cron_manager":
            from .cron.manager import CronManager
            return CronManager()
        case "restart_scheduler":
            from .cron.restart_scheduler import RestartScheduler
            return RestartScheduler(runtime.resource("cron_manager"))
        case "dns_manager":
            from .dns.manager import SimpleDNSManager
            configuration = runtime.resource("dynamic_configuration")
            return SimpleDNSManager(
                configuration=lambda: configuration.dns,
                docker_manager=runtime.resource("docker_mc_manager"),
            )
        case "login_code_manager":
            from .auth.login_code import LoginCodeManager
            return LoginCodeManager()
        case "skin_fetcher":
            from .players.skin_fetcher import SkinFetcher
            return SkinFetcher()
        case "player_service":
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
                publish=runtime.resource("event_bus").publish,
                spawn=lambda coroutine: runtime.spawn(coroutine, name="player-skin-update"),
                skin_client=runtime.resource("skin_fetcher"),
                resolve_name=resolve_name,
                ignored_name=ignored_name,
            )
        case "heartbeat_manager":
            from .players.heartbeat import HeartbeatManager
            return HeartbeatManager(runtime.resource("player_service"))
        case "player_syncer":
            from .players.player_syncer import PlayerSyncer
            return PlayerSyncer(runtime.resource("player_service"))
        case "log_monitor":
            from .log_monitor.monitor import LogMonitor
            return LogMonitor(runtime.resource("player_service"))
        case "identity_service":
            from .auth.service import IdentityService
            return IdentityService(settings=runtime.settings, session_factory=runtime.database.session_factory)
        case "self_check_notifications":
            from .self_check.notifications import SelfCheckNotificationBus
            return SelfCheckNotificationBus()
        case "self_check_dependencies":
            from .self_check.checks.base import SelfCheckDependencies
            return SelfCheckDependencies(
                settings=runtime.settings,
                configuration=runtime.resource("dynamic_configuration"),
                minecraft=runtime.resource("docker_mc_manager"),
                snapshots=runtime.resource("snapshot_service"),
                connectivity=runtime.resource("dns_manager"),
                logs=runtime.resource("log_monitor"),
                locks=runtime.resource("server_operation_lock"),
            )
        case "self_check_service":
            from .self_check.service import SelfCheckService
            return SelfCheckService(
                session_factory=runtime.database.session_factory,
                dependencies=runtime.resource("self_check_dependencies"),
                notifications=runtime.resource("self_check_notifications"),
            )
        case "archive_upload_sessions" | "file_upload_sessions" | "process_cache":
            return {}
        case "archive_upload_lock" | "server_sync_lock":
            import asyncio
            return asyncio.Lock()
        case _:
            raise KeyError(f"Unknown runtime resource: {name}")
