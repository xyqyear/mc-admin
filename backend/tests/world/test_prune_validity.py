import asyncio
import gzip
import struct
import zlib
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import cast

import pytest
from sqlalchemy import select

from app.background_tasks import TaskStatus
from app.background_tasks.manager import BackgroundTaskManager
from app.chunk_prune.inputs import PrunePreviewConflict
from app.chunk_prune.lifecycle import PrunePreviewRegistry
from app.chunk_prune.models import ChunkPrunePreviewRequest
from app.chunk_prune.service import ChunkPruneService
from app.db.metadata import Base
from app.dynamic_config import get_config, get_config_manager
from app.mcmap import runner
from app.minecraft import DockerMCManager, MCServerStatus
from app.operations.journal import OperationJournal
from app.operations.journal_types import (
    OperationSpec,
    OperationState,
    RecoveryReference,
    ResourceReference,
)
from app.servers.models import Server, ServerStatus
from app.utils import async_fs
from app.world.locks import ServerOperationLock

pytestmark = [pytest.mark.binary("mcmap"), pytest.mark.binary("fd")]
TEAM = "11111111-1111-4111-8111-111111111111"


def text_tag(name: str, value: str) -> bytes:
    return b"\x08" + struct.pack(">H", len(name)) + name.encode() + struct.pack(">H", len(value)) + value.encode()


def region_bytes() -> bytes:
    data = bytearray(8192)
    for x in range(2):
        payload = b"\x0a\x00\x00"
        for name, value in (("DataVersion", 4671), ("xPos", x), ("zPos", 0)):
            payload += b"\x03" + struct.pack(">H", len(name)) + name.encode() + struct.pack(">i", value)
        payload += b"\x04\x00\x0dInhabitedTime" + struct.pack(">q", 0)
        payload += text_tag("Status", "minecraft:full") + text_tag("marker", f"chunk-{x}") + b"\x00"
        compressed = zlib.compress(payload)
        sector = bytearray(4096)
        struct.pack_into(">I", sector, 0, len(compressed) + 1)
        sector[4] = 2
        sector[5:5 + len(compressed)] = compressed
        struct.pack_into(">I", data, x * 4, ((len(data) // 4096) << 8) | 1)
        data.extend(sector)
    return bytes(data)


class StoppedDocker:
    def get_instance(self, server_id):
        return self

    async def get_status(self):
        return MCServerStatus.EXISTS


@pytest.fixture
async def prune_case(isolated_runtime, tmp_path):
    runtime = isolated_runtime
    project = runtime.settings.server_path / "survival"
    data = project / "data"
    region = data / "world" / "region" / "r.0.0.mca"
    region.parent.mkdir(parents=True)
    region.write_bytes(region_bytes())
    (data / "world" / "level.dat").write_bytes(gzip.compress(b"\x0a\x00\x00\x00"))
    (data / "server.properties").write_text("level-name=world\n")
    (project / "compose.yaml").write_text("services: {mc: {container_name: mc-survival, image: minecraft}}\n")
    claims = data / "world" / "ftbchunks" / f"{TEAM}.snbt"
    claims.parent.mkdir()
    claims.write_text('{chunks: {"minecraft:overworld": [{x: 0, z: 0, force_loaded: 1b}]}}')
    teams = data / "world" / "ftbteams" / "party"
    teams.mkdir(parents=True)
    (teams / f"{TEAM}.snbt").write_text('{type: "party", properties: {"ftbteams:display_name": "builders"}}')
    async with runtime.database.engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with runtime.database.session_factory() as session:
        session.add(Server(server_id="survival"))
        await session.commit()
    await get_config_manager().initialize_all_configs()
    journal = OperationJournal(runtime.database.session_factory)
    runtime.journal = journal
    manager = BackgroundTaskManager(journal)
    runtime.resources["task_manager"] = manager
    lock = ServerOperationLock()
    service = ChunkPruneService(docker=cast(DockerMCManager, StoppedDocker()), operation_lock=lock, temp_base_dir=tmp_path / "prune")
    runtime.resources["chunk_prune_service"] = service
    await service.start()
    try:
        yield service, manager, journal, region, claims, runtime
    finally:
        await runtime.close()


async def wait_task(manager, task_id):
    async with asyncio.timeout(20):
        while True:
            task = manager.get_task(task_id)
            assert task is not None
            if task.status in {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED}:
                await asyncio.sleep(0)
                return task
            await asyncio.sleep(.01)


async def preview(case, actor_id: int | None = None):
    service, manager, journal, *_ = case
    task_id = await service.start_preview(server_id="survival", request=ChunkPrunePreviewRequest(mode="chunks", threshold_seconds=3600), user_id=actor_id)
    task = await wait_task(manager, task_id)
    assert task.status == TaskStatus.COMPLETED, task.error
    assert task.result["chunks_selected"] == 1
    record = await journal.get(task_id)
    assert record.state == OperationState.SUCCEEDED
    assert record.writers_stopped and not record.processes
    return service.registry.metadata[task_id]


def conflict_code(error) -> str:
    assert isinstance(error, PrunePreviewConflict)
    return cast(dict[str, str], error.detail)["code"]


def pause_apply(monkeypatch):
    original = runner.prune_inhabited
    entered, release = asyncio.Event(), asyncio.Event()

    @asynccontextmanager
    async def gated(**kwargs):
        if not kwargs["dry_run"]:
            entered.set()
            await release.wait()
        async with original(**kwargs) as process:
            yield process

    monkeypatch.setattr(runner, "prune_inhabited", gated)
    return entered, release


@pytest.mark.parametrize("change", ["world", "claims", "generation"])
async def test_completed_preview_rejects_changed_inputs_without_accepting_a_writer(prune_case, change):
    service, manager, journal, region, claims, runtime = prune_case
    dry_run = await preview(prune_case)
    if change == "world":
        region.write_bytes(region.read_bytes() + b"external change")
    elif change == "claims":
        claims.write_text('{chunks: {"minecraft:overworld": [{x: 0, z: 0}, {x: 1, z: 0}]}}')
    else:
        async with runtime.database.session_factory() as session:
            previous = await session.scalar(select(Server).where(Server.status == ServerStatus.ACTIVE))
            previous.status = ServerStatus.REMOVED
            await session.flush()
            session.add(Server(server_id="survival"))
            await session.commit()
    before = region.read_bytes()
    with pytest.raises(PrunePreviewConflict) as caught:
        await service.start_apply(server_id="survival", preview_task_id=dry_run.task_id)
    assert conflict_code(caught.value) == "prune_preview_stale"
    assert region.read_bytes() == before
    assert len(manager.get_all_tasks()) == 1
    assert len(await journal.list()) == 1
    assert dry_run.references == 0 and dry_run.apply_task_id is None


async def test_accepted_apply_rechecks_inputs_before_starting_the_writer(prune_case, monkeypatch):
    service, manager, journal, region, *_ = prune_case
    dry_run = await preview(prune_case)
    started, release = asyncio.Event(), asyncio.Event()
    original = journal.start

    async def gated_start(operation_id):
        started.set()
        await release.wait()
        return await original(operation_id)

    monkeypatch.setattr(journal, "start", gated_start)
    apply_id = await service.start_apply(server_id="survival", preview_task_id=dry_run.task_id)
    await asyncio.wait_for(started.wait(), 5)
    region.write_bytes(region.read_bytes() + b"changed after acceptance")
    before = region.read_bytes()
    release.set()
    result = await wait_task(manager, apply_id)
    assert result.status == TaskStatus.FAILED
    assert result.error_code == "prune_preview_stale"
    record = await journal.get(apply_id)
    assert record.failure_code == "prune_preview_stale"
    assert not record.data_changed and record.writers_stopped and not record.processes
    assert region.read_bytes() == before
    assert dry_run.references == 0


async def test_apply_rejects_external_tile_cache_before_changing_world(prune_case, tmp_path):
    service, manager, journal, region, *_ = prune_case
    dry_run = await preview(prune_case)
    before = region.read_bytes()
    external_tiles = tmp_path / "external-tiles"
    external_png = external_tiles / "world" / "region" / "r.0.0.png"
    external_png.parent.mkdir(parents=True)
    external_png.write_bytes(b"owned external PNG must survive")
    cache = dry_run.data_path / ".mcmap"
    cache.mkdir(exist_ok=True)
    (cache / "tiles").symlink_to(external_tiles, target_is_directory=True)

    apply_id = await service.start_apply(server_id="survival", preview_task_id=dry_run.task_id)
    result = await wait_task(manager, apply_id)

    assert result.status == TaskStatus.FAILED
    assert region.read_bytes() == before
    assert external_png.read_bytes() == b"owned external PNG must survive"
    record = await journal.get(apply_id)
    assert record.state == OperationState.FAILED
    assert not record.data_changed and record.writers_stopped and not record.processes
    assert dry_run.references == 0


async def test_concurrent_apply_accepts_one_writer_and_preserves_claimed_chunk(prune_case):
    service, manager, journal, region, *_ = prune_case
    dry_run = await preview(prune_case)
    results = await asyncio.gather(*(
        service.start_apply(server_id="survival", preview_task_id=dry_run.task_id) for _ in range(2)
    ), return_exceptions=True)
    accepted = [result for result in results if isinstance(result, str)]
    rejected = [result for result in results if isinstance(result, BaseException)]
    assert len(accepted) == len(rejected) == 1
    assert conflict_code(rejected[0]) == "prune_preview_consumed"
    result = await wait_task(manager, accepted[0])
    assert result.status == TaskStatus.COMPLETED, result.error
    data = region.read_bytes()
    assert data[:4] != b"\0" * 4
    assert data[4:8] == b"\0" * 4
    assert len(await journal.list()) == 2
    assert dry_run.references == 0


async def test_dismiss_and_expiry_keep_artifacts_until_the_actual_apply_finishes(prune_case, monkeypatch):
    service, manager, journal, region, *_ = prune_case
    dry_run = await preview(prune_case)
    claims_file = dry_run.claims_file
    assert claims_file is not None
    payload = claims_file.read_bytes()
    entered, release = pause_apply(monkeypatch)
    apply_id = await service.start_apply(server_id="survival", preview_task_id=dry_run.task_id)
    await asyncio.wait_for(entered.wait(), 5)
    assert manager.remove_task(dry_run.task_id)
    monkeypatch.setattr(service.registry, "now", lambda: datetime.now(UTC) + timedelta(days=1))
    await service.registry.reap()
    assert claims_file.read_bytes() == payload
    assert service.get_preview_geometry(server_id="survival", preview_task_id=dry_run.task_id).dimensions
    assert any(task.task_id == dry_run.task_id for task in service.registry.tasks("survival"))
    release.set()
    result = await wait_task(manager, apply_id)
    assert result.status == TaskStatus.COMPLETED, result.error
    assert dry_run.references == 0
    await service.registry.reap()
    assert not claims_file.exists()
    assert region.read_bytes()[4:8] == b"\0" * 4
    record = await journal.get(apply_id)
    assert record.writers_stopped and all(reference.resolved for reference in record.recovery_refs)


async def test_dynamic_expiry_refuses_apply_before_consuming_the_preview(prune_case, monkeypatch):
    service, manager, journal, region, *_ = prune_case
    dry_run = await preview(prune_case)
    before = region.read_bytes()
    monkeypatch.setattr(get_config().mcmap, "prune_preview_ttl_seconds", 1)
    monkeypatch.setattr(service.registry, "now", lambda: datetime.now(UTC) + timedelta(seconds=2))
    with pytest.raises(PrunePreviewConflict) as caught:
        await service.start_apply(server_id="survival", preview_task_id=dry_run.task_id)
    assert conflict_code(caught.value) == "prune_preview_expired"
    assert dry_run.references == 0 and dry_run.apply_task_id is None
    assert region.read_bytes() == before
    assert len(manager.get_all_tasks()) == len(await journal.list()) == 1
    claims_file = dry_run.claims_file
    assert claims_file is not None
    await service.registry.reap()
    assert not claims_file.exists()


async def test_cancellation_before_worker_body_releases_preview_reference(prune_case):
    service, manager, journal, region, *_ = prune_case
    dry_run = await preview(prune_case)
    before = region.read_bytes()
    apply_id = await service.start_apply(server_id="survival", preview_task_id=dry_run.task_id)
    assert manager.get_task(apply_id).started_at is None
    assert await manager.cancel(apply_id)
    result = await wait_task(manager, apply_id)
    assert result.status == TaskStatus.CANCELLED
    assert dry_run.references == 0
    assert region.read_bytes() == before
    await service.registry.reap()
    assert not (service.registry.base_dir / dry_run.task_id).exists()
    record = await journal.get(apply_id)
    assert record.state == OperationState.CANCELLED and record.writers_stopped


async def test_cancelling_an_active_apply_releases_lease_and_artifact_reference(prune_case, monkeypatch):
    service, manager, journal, region, *_ = prune_case
    dry_run = await preview(prune_case)
    before = region.read_bytes()
    entered, _ = pause_apply(monkeypatch)
    apply_id = await service.start_apply(server_id="survival", preview_task_id=dry_run.task_id)
    await asyncio.wait_for(entered.wait(), 5)
    assert await manager.cancel(apply_id)
    result = await wait_task(manager, apply_id)
    assert result.status == TaskStatus.CANCELLED
    assert dry_run.references == 0
    assert not service._operation_lock.is_locked("survival")
    assert region.read_bytes() == before
    record = await journal.get(apply_id)
    assert record.state == OperationState.CANCELLED and record.writers_stopped
    assert all(reference.resolved for reference in record.recovery_refs)
    await service.registry.reap()
    assert not (service.registry.base_dir / dry_run.task_id).exists()


async def test_startup_reaping_preserves_unresolved_journal_artifacts_until_explicit_resolution(prune_case):
    service, _, journal, *_ = prune_case
    dry_run = await preview(prune_case)
    artifact = service.registry.base_dir / dry_run.task_id
    await journal.accept(OperationSpec(
        "chunk_prune_apply", (ResourceReference("files", "survival", dry_run.reference.generation, "data"),),
        operation_id="interrupted-apply",
    ))
    await journal.start("interrupted-apply")
    await journal.phase("interrupted-apply", "pruning_world", recovery_refs=[RecoveryReference("prune_preview", dry_run.task_id)])
    await journal.finish("interrupted-apply", OperationState.INTERRUPTED, writers_stopped=True)
    await service.close()
    assert artifact.is_dir()
    orphan = service.registry.base_dir / ("a" * 32)
    orphan.mkdir()
    registry = PrunePreviewRegistry(service.registry.base_dir)
    try:
        await registry.start()
        assert artifact.is_dir() and not orphan.exists()
        await journal.resolve_reference("interrupted-apply", "prune_preview", dry_run.task_id)
        await registry.reap()
        assert not artifact.exists()
    finally:
        await registry.close()


async def test_apply_attributes_the_actual_actor_without_rewriting_preview_history(prune_case):
    service, manager, journal, *_ = prune_case
    dry_run = await preview(prune_case, actor_id=11)
    apply_id = await service.start_apply(server_id="survival", preview_task_id=dry_run.task_id, user_id=22)
    result = await wait_task(manager, apply_id)
    assert result.status == TaskStatus.COMPLETED, result.error
    assert dry_run.user_id == 11
    assert service.registry.metadata[apply_id].user_id == 22
    preview_record = await journal.get(dry_run.task_id)
    apply_record = await journal.get(apply_id)
    assert preview_record.actor_id == 11
    assert apply_record.actor_id == 22


async def test_reaper_preserves_preview_created_while_directory_enumeration_is_pending(prune_case, monkeypatch):
    service, *_ = prune_case
    entered, release = asyncio.Event(), asyncio.Event()
    original = async_fs.iterdir
    armed = True

    async def paused_iterdir(path):
        nonlocal armed
        if path == service.registry.base_dir and armed:
            armed = False
            entered.set()
            await release.wait()
        return await original(path)

    monkeypatch.setattr(async_fs, "iterdir", paused_iterdir)
    cleanup = asyncio.create_task(service.registry.reap())
    try:
        await asyncio.wait_for(entered.wait(), 5)
        dry_run = await preview(prune_case)
        artifact = service.registry.base_dir / dry_run.task_id
        claims_file = dry_run.claims_file
        assert claims_file is not None
        payload = claims_file.read_bytes()
        release.set()
        await asyncio.wait_for(cleanup, 5)
        assert artifact.is_dir()
        assert claims_file.read_bytes() == payload
        assert service.registry.state(dry_run).availability == "ready"
        assert service.get_preview_geometry(server_id="survival", preview_task_id=dry_run.task_id).dimensions
    finally:
        release.set()
        await cleanup
