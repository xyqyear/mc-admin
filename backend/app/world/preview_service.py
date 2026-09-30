"""Runtime-owned map preview sessions and rendering."""

import asyncio
from collections.abc import AsyncGenerator
from contextlib import aclosing
from pathlib import Path

from app.snapshots.selection_models import RestorationSelection

from ..config import get_settings
from ..operations.coordinator import ResourceClaim, ResourceKind
from ..operations.execution import operation_scope
from ..runtime_resources import current_runtime
from ..servers.references import ServerRef, resolve_server_ref, revalidate_server_ref
from ..snapshots import SnapshotService
from ..snapshots.restoration_store import (
    SessionFactory,
)
from .artifacts import artifact_root, reap_restore_stages
from .events import (
    PreviewEvent,
)
from .preview import PreviewSessionManager
from .preview_application import WorldPreviewApplication
from .scope_execution import RestoreScopeExecutor


class WorldPreviewService:
    def __init__(
        self,
        *,
        snapshot_service: SnapshotService,
        session_factory: SessionFactory,
        preview_base_dir: Path | None = None,
        servers_root: Path | None = None,
    ) -> None:
        settings = get_settings()

        self._snapshots = snapshot_service
        self._session_factory = session_factory
        self._servers_root = (
            servers_root if servers_root is not None else settings.server_path
        )
        self._executor = RestoreScopeExecutor(snapshot_service)
        self._preview_manager = PreviewSessionManager(
            preview_base_dir
            if preview_base_dir is not None
            else artifact_root("restore"),
            snapshot_service.repository_use,
        )
        self._previews = WorldPreviewApplication(
            snapshot_service, self._executor, self._preview_manager
        )

    async def _reference(self, server_id: str) -> ServerRef:
        async with self._session_factory() as session:
            return await resolve_server_ref(
                session, server_id, servers_root=self._servers_root
            )

    async def prepare(self) -> None:
        await self._preview_manager.reap_orphan_dirs()
        await reap_restore_stages()

    async def _revalidate(self, reference: ServerRef) -> None:
        async with self._session_factory() as session:
            await revalidate_server_ref(session, reference)

    async def begin_preview(
        self, server_id: str, source_snapshot_id: str, selection: RestorationSelection
    ) -> AsyncGenerator[PreviewEvent]:
        reference = await self._reference(server_id)
        async with operation_scope(
            "world_preview",
            [server_id],
            claims=[ResourceClaim(ResourceKind.MAP_CACHE, server_id)],
        ):
            await self._revalidate(reference)
            async with aclosing(
                self._previews.begin_preview(
                    server_id,
                    reference.data_path,
                    source_snapshot_id,
                    selection,
                    reference.generation,
                )
            ) as events:
                async for event in events:
                    yield event

    async def require_preview_owner(
        self, server_id: str, session_id: str, *, missing_ok: bool = False
    ) -> None:
        from .preview import PreviewSessionNotFoundError

        session = self._preview_manager.get_session(session_id)
        if session is None:
            if missing_ok:
                return
            raise PreviewSessionNotFoundError(session_id)
        reference = await self._reference(server_id)
        if (
            session.server_id != server_id
            or session.server_generation != reference.generation
        ):
            raise PreviewSessionNotFoundError(session_id)

    async def request_preview_tile(
        self, session_id: str, rx: int, rz: int, *, timeout: float | None = None
    ) -> Path:
        return await self._previews.request_preview_tile(
            session_id, rx, rz, timeout=timeout
        )

    async def read_preview_tile(
        self, session_id: str, rx: int, rz: int, *, timeout: float | None = None
    ) -> bytes:
        return await self._previews.read_preview_tile(
            session_id, rx, rz, timeout=timeout
        )

    async def end_preview(self, session_id: str) -> None:
        await self._preview_manager.end(session_id)

    def heartbeat_preview(self, session_id: str) -> None:
        self._preview_manager.heartbeat(session_id)

    async def get_preview_tile(self, session_id: str, rx: int, rz: int) -> Path | None:
        return await self._preview_manager.get_tile_path(session_id, rx, rz)

    def get_preview_session_dir(self, session_id: str) -> Path | None:
        return self._preview_manager.get_session_dir(session_id)

    def start_janitor(self) -> asyncio.Task:
        return self._preview_manager.start_janitor()

    async def stop_janitor(self) -> None:
        await self._preview_manager.stop_janitor()

    async def close(self, *, preserve_artifacts: bool = False) -> None:
        await self._preview_manager.close(preserve_artifacts=preserve_artifacts)


def get_world_preview_service() -> WorldPreviewService | None:
    return current_runtime().resource("world_preview_service")
