import asyncio
import json
from contextlib import aclosing
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock

import pytest

from app.background_tasks import (
    BackgroundTask,
    BackgroundTaskManager,
    TaskStatus,
    TaskType,
)
from app.chunk_prune import lifecycle
from app.chunk_prune.inputs import PruneInputVersion, PrunePreviewConflict
from app.chunk_prune.models import ChunkPruneTaskMetadata
from app.chunk_prune.service import ChunkPruneService
from app.db.metadata import Base
from app.dynamic_config import ConfigProxy
from app.execution_observation import snapshot
from app.minecraft import DockerMCManager, MCServerStatus
from app.operations.journal import OperationJournal
from app.operations.journal_types import (
    OperationSpec,
    OperationState,
    ResourceReference,
)
from app.servers.references import ServerRef
from app.snapshots.restoration_models import (
    Restoration,
    RestorationStatus,
    RestorationType,
)
from tests.support.runtime import replace_runtime_resource


@pytest.fixture
async def domain(isolated_runtime, tmp_path):
    runtime = isolated_runtime
    async with runtime.database.engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    runtime.journal = OperationJournal(runtime.database.session_factory)
    manager = BackgroundTaskManager(runtime.journal)
    replace_runtime_resource(runtime, "task_manager", manager)
    config = SimpleNamespace(mcmap=SimpleNamespace(prune_preview_ttl_seconds=3600))
    replace_runtime_resource(runtime, "dynamic_configuration", config)
    docker = SimpleNamespace(get_instance=lambda _: SimpleNamespace(get_status=AsyncMock(return_value=MCServerStatus.EXISTS)))
    service = ChunkPruneService(docker=cast(DockerMCManager, docker), operation_lock=runtime.server_operation_lock,
                                temp_base_dir=tmp_path / "previews")
    replace_runtime_resource(runtime, "chunk_prune_service", service)
    await service.start()
    try:
        yield SimpleNamespace(runtime=runtime, manager=manager, service=service, config=config)
    finally:
        await manager.shutdown()
        await service.close()


async def next_matching(stream, predicate):
    async with asyncio.timeout(2):
        while True:
            frame = await anext(stream)
            if frame.startswith(b"data: "):
                event = json.loads(frame[6:])
                if predicate(event):
                    return event


def retained_preview(domain, *, completed_at=None):
    root = domain.service.registry.base_dir
    task = BackgroundTask(task_id="preview", task_type=TaskType.CHUNK_PRUNE_PREVIEW,
                          server_id="survival", name="裁剪预览", status=TaskStatus.COMPLETED,
                          result={"dry_run": True, "chunks_selected": 1})
    metadata = ChunkPruneTaskMetadata(
        task_id=task.task_id, server_id="survival", operation="preview", data_path=root,
        mode="chunks", threshold_seconds=30, threshold_ticks=600, task=task,
        reference=ServerRef("survival", 1, root, root, root),
        inputs=PruneInputVersion(1, str(root), 600, "chunks", "before", "claims"),
        completed_at=completed_at or datetime.now(UTC),
        result=task.result,
    )
    domain.manager._tasks[task.task_id] = task
    domain.service.registry.metadata[task.task_id] = metadata
    domain.service.registry.changed()
    return metadata


async def test_restoration_index_contains_all_pending_global_targets_without_memory_tasks(domain):
    targets = [{"server_id": "survival", "generation": 1}, {"server_id": "creative", "generation": 4}]
    for index in range(101):
        operation_id = f"restore-{index}"
        await domain.runtime.journal.accept(OperationSpec(
            "snapshot_restore", (ResourceReference("files"),), operation_id=operation_id,
            origin="task", legacy_id=operation_id,
        ))
    async with domain.runtime.database.session_factory() as session:
        session.add_all([Restoration(
            id=f"restoration-{index}", operation_id=f"restore-{index}", type=RestorationType.GLOBAL,
            source_snapshot_id="a" * 64, selection_json="{}", status=RestorationStatus.PENDING,
            scope_json=json.dumps({"scope": {"kind": "global"}}), targets_json=json.dumps(targets),
        ) for index in range(101)])
        await session.commit()
    assert domain.manager.get_all_tasks() == []
    async with aclosing(domain.manager.events(get_index=snapshot)) as stream:
        initial = await next_matching(stream, lambda event: event["type"] == "snapshot")
    assert len(initial["active_restorations"]) == 101
    assert all(row["status"] == "pending" and row["scope"] == {"kind": "global"}
               and row["targets"] == targets for row in initial["active_restorations"])
    await domain.runtime.journal.start("restore-0")
    async with domain.runtime.database.session_factory() as session:
        row = await session.get(Restoration, "restoration-0")
        assert row is not None
        row.status = RestorationStatus.SUCCEEDED
        await session.commit()
    assert next(row for row in await snapshot("restorations") if row["id"] == "restoration-0")["status"] == "running"
    await domain.runtime.journal.finish("restore-0", OperationState.SUCCEEDED, writers_stopped=True)
    task = BackgroundTask(task_id="restore-0", task_type=TaskType.SNAPSHOT_RESTORE,
                          name="正在结束恢复", status=TaskStatus.RUNNING)
    domain.manager._tasks[task.task_id] = task
    retained = await snapshot("restorations")
    assert len(retained) == 101
    assert next(row for row in retained if row["id"] == "restoration-0")["status"] == "running"
    task.status = TaskStatus.COMPLETED
    assert len(await snapshot("restorations")) == 100


async def test_dismissed_preview_expires_by_event_without_scanning_or_losing_result(domain, monkeypatch):
    domain.config.mcmap.prune_preview_ttl_seconds = 1
    preview = retained_preview(domain)
    assert domain.manager.remove_task(preview.task_id)
    reaper = AsyncMock(side_effect=AssertionError("expiry must not scan filesystem"))
    monkeypatch.setattr(domain.service.registry, "reap", reaper)
    expiry = domain.service.registry._expiry
    assert expiry is not None
    try:
        async with aclosing(domain.manager.events(get_index=snapshot)) as stream:
            initial = await next_matching(stream, lambda event: event["type"] == "snapshot")
            assert initial["tasks"] == []
            retained = initial["prune_states"][0]
            assert retained["preview"]["availability"] == "ready"
            assert retained["preview_task"]["result_included"]
            assert retained["preview_task"]["result"] == {"dry_run": True, "chunks_selected": 1}
            preview.completed_at = datetime.now(UTC) - timedelta(seconds=.9)
            domain.service.registry.changed()
            expired = await next_matching(stream, lambda event: event["type"] == "prune_state"
                                          and event["prune_states"][0]["preview"]["availability"] == "expired")
            assert expired["prune_states"][0]["preview_task"]["task_id"] == preview.task_id
        reaper.assert_not_awaited()
    finally:
        monkeypatch.undo()
        await domain.service.close()
    assert expiry.done() and domain.service.registry._expiry is None


async def test_consumption_and_external_input_rejection_are_published_before_any_writer(domain, monkeypatch):
    preview = retained_preview(domain)
    entered, release = asyncio.Event(), asyncio.Event()

    async def changed_inputs(_):
        entered.set()
        await release.wait()
        return PruneInputVersion(1, str(preview.data_path), 600, "chunks", "external-change", "claims"), None

    monkeypatch.setattr("app.chunk_prune.service.require_supported_adapter", AsyncMock())
    monkeypatch.setattr(domain.service, "_capture_inputs", changed_inputs)
    async with aclosing(domain.manager.events(get_index=snapshot)) as stream:
        await next_matching(stream, lambda event: event["type"] == "snapshot")
        applying = asyncio.create_task(domain.service.start_apply(server_id="survival", preview_task_id=preview.task_id))
        try:
            await asyncio.wait_for(entered.wait(), 2)
            consumed = await next_matching(stream, lambda event: event["type"] == "prune_state"
                                           and event["prune_states"][0]["preview"]["availability"] == "consumed")
            assert consumed["prune_states"][0]["preview"]["apply_task_id"]
            release.set()
            with pytest.raises(PrunePreviewConflict):
                await applying
            stale = await next_matching(stream, lambda event: event["type"] == "prune_state"
                                        and event["prune_states"][0]["preview"]["availability"] == "stale")
            assert stale["prune_states"][0]["preview"]["apply_task_id"] is None
            assert len(domain.manager.get_all_tasks()) == 1
            assert await domain.runtime.journal.list() == []
            assert preview.references == 0
        finally:
            release.set()
            await asyncio.gather(applying, return_exceptions=True)


async def test_eviction_removes_retained_domain_index(domain, monkeypatch):
    preview = retained_preview(domain)
    preview.unavailable_reason = "stale"
    assert domain.manager.remove_task(preview.task_id)
    monkeypatch.setattr(lifecycle, "MAX_RETAINED_PREVIEWS", 1)
    async with aclosing(domain.manager.events(get_index=snapshot)) as stream:
        await next_matching(stream, lambda event: event["type"] == "snapshot")
        await domain.service.registry.reserve_capacity()
        removed = await next_matching(stream, lambda event: event["type"] == "prune_state" and not event["prune_states"])
        assert removed["prune_states"] == []
    assert not domain.service.registry.metadata


async def test_committed_mcmap_config_update_and_reset_rearm_streamed_preview_expiry(domain, monkeypatch):
    manager = domain.runtime.config_manager
    await manager.initialize_all_configs()
    replace_runtime_resource(domain.runtime, "dynamic_configuration", ConfigProxy(manager))
    preview = retained_preview(domain, completed_at=datetime.now(UTC) - timedelta(seconds=10))
    reaper = AsyncMock(side_effect=AssertionError("configuration notification must not scan artifacts"))
    original_reaper = domain.service.registry.reap
    monkeypatch.setattr(domain.service.registry, "reap", reaper)
    try:
        async with aclosing(domain.manager.events(get_index=snapshot)) as stream:
            initial = await next_matching(stream, lambda event: event["type"] == "snapshot")
            previous = initial["prune_states"][0]["preview"]
            assert previous["availability"] == "ready"
            data = manager.get_config("mcmap").model_dump(mode="json")
            await manager.update_config("mcmap", {**data, "prune_preview_ttl_seconds": 1})
            expired = await next_matching(stream, lambda event: event["type"] == "prune_state"
                                          and event["prune_states"][0]["preview"]["availability"] == "expired")
            assert expired["prune_states"][0]["preview"]["expires_at"] != previous["expires_at"]
            await manager.reset_config("mcmap")
            reset = await next_matching(stream, lambda event: event["type"] == "prune_state"
                                        and event["prune_states"][0]["preview"]["availability"] == "ready")
            assert reset["prune_states"][0]["preview"]["expires_at"] == previous["expires_at"]
            assert reset["prune_states"][0]["preview"]["task_id"] == preview.task_id
        reaper.assert_not_awaited()
    finally:
        monkeypatch.setattr(domain.service.registry, "reap", original_reaper)
        await domain.service.close()
    assert domain.service.registry.changed not in manager._listeners.get("mcmap", ())
