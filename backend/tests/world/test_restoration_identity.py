import json
from datetime import UTC, datetime
from typing import cast
from unittest.mock import Mock

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.background_tasks.manager import BackgroundTaskManager
from app.db.metadata import Base
from app.minecraft import DockerMCManager
from app.servers.models import Server, ServerStatus
from app.servers.references import resolve_server_ref
from app.snapshots import SnapshotService
from app.snapshots.commands import SnapshotCommands
from app.snapshots.restoration_models import (
    Restoration,
    RestorationStatus,
    RestorationType,
)
from app.snapshots.restoration_store import RestorationStore, restoration_binding_issue
from app.world import ServerOperationLock
from tests.support.restorations import legacy_world_restoration


@pytest.fixture
async def identity_case(tmp_path):
    root = tmp_path / "servers"
    project = root / "survival"
    region = project / "data" / "world" / "region"
    region.mkdir(parents=True)
    (project / "compose.yaml").write_text(
        "services: {mc: {container_name: mc-survival, image: minecraft}}\n"
    )
    (region.parent / "level.dat").write_bytes(b"world metadata")
    (region / "r.0.0.mca").write_bytes(b"replacement world data")
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'identity.sqlite3'}")
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with sessions() as session:
        session.add(Server(server_id="survival"))
        await session.commit()
        reference = await resolve_server_ref(session, "survival", servers_root=root)
    snapshots = Mock(spec=SnapshotService)
    from app.snapshots.repository_use import RepositoryUse

    snapshots.repository_use = RepositoryUse()
    docker = Mock(spec=DockerMCManager)
    orchestrator = SnapshotCommands(
        cast(SnapshotService, snapshots),
        cast(DockerMCManager, docker),
        ServerOperationLock(),
        BackgroundTaskManager(),
        sessions,
        root,
    )
    try:
        yield orchestrator, sessions, reference, region, snapshots, docker
    finally:
        await engine.dispose()


async def retire_and_replace(sessions):
    async with sessions() as session:
        old = await session.scalar(
            select(Server).where(Server.status == ServerStatus.ACTIVE)
        )
        assert old is not None
        old.status = ServerStatus.REMOVED
        old.updated_at = datetime.now(UTC)
        await session.flush()
        replacement = Server(server_id=old.server_id)
        session.add(replacement)
        await session.commit()
        return replacement.id


async def test_rollback_refuses_retired_generation_before_any_snapshot_or_docker_action(
    identity_case,
):
    orchestrator, sessions, reference, region, snapshots, docker = identity_case
    store = RestorationStore(sessions)
    async with sessions() as session:
        session.add(
            legacy_world_restoration(
                "old-restoration",
                reference,
                "retained-source",
                "retained-safety",
                ["world/poi"],
            )
        )
        await session.commit()
    replacement = await retire_and_replace(sessions)
    with pytest.raises(HTTPException) as caught:
        await orchestrator.rollback("old-restoration", 1)
    assert caught.value.status_code == 409
    detail = cast(dict[str, str], caught.value.detail)
    assert detail["code"] == "restoration_identity_conflict"
    assert detail["message"]
    assert (region / "r.0.0.mca").read_bytes() == b"replacement world data"
    snapshots.create_snapshot.assert_not_called()
    snapshots.restore.assert_not_called()
    docker.get_instance.assert_not_called()
    row = await store.get("old-restoration")
    assert row is not None
    assert row.server_generation == reference.generation < replacement
    assert row.source_snapshot_id == "retained-source"
    assert row.safety_snapshot_id == "retained-safety"
    assert row.status == RestorationStatus.SUCCEEDED
    assert row.binding_issue is None
    assert restoration_binding_issue(row, replacement) == "generation_changed"


@pytest.mark.parametrize(
    "generation,issue",
    [(None, None), (None, "generation_uncertain"), (1, "generation_uncertain")],
)
async def test_uncertain_legacy_history_is_readable_but_never_authorizes_rollback(
    identity_case, generation, issue
):
    orchestrator, sessions, reference, region, snapshots, docker = identity_case
    async with sessions() as session:
        session.add(
            Restoration(
                id="legacy",
                server_id="survival",
                server_generation=generation,
                binding_issue=issue,
                type=RestorationType.WORLD,
                source_snapshot_id="source",
                safety_snapshot_id="safety",
                selection_json='{"type":"world"}',
                status=RestorationStatus.INTERRUPTED,
                scope_json=json.dumps(
                    {
                        "scope": {
                            "kind": "world",
                            "server_id": "survival",
                            "selection": {"type": "world"},
                        }
                    }
                ),
            )
        )
        await session.commit()
    with pytest.raises(HTTPException) as caught:
        await orchestrator.rollback("legacy", 1)
    assert caught.value.status_code == 409
    assert (
        cast(dict[str, str], caught.value.detail)["code"]
        == "restoration_identity_conflict"
    )
    row = await RestorationStore(sessions).get("legacy")
    assert row is not None
    assert row.server_generation == generation
    assert row.binding_issue == issue
    assert (
        restoration_binding_issue(row, reference.generation) == "generation_uncertain"
    )
    assert (region / "r.0.0.mca").read_bytes() == b"replacement world data"
    snapshots.create_snapshot.assert_not_called()
    snapshots.restore.assert_not_called()
    docker.get_instance.assert_not_called()
