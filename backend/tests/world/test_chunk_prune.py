from contextlib import asynccontextmanager
from datetime import timedelta

import pytest

from app.background_tasks import TaskProgress, TaskStatus, TaskType, task_manager
from app.chunk_prune.models import (
    ChunkPrunePreviewGeometryResponse,
    ChunkPruneTaskMetadata,
)
from app.chunk_prune.service import (
    ChunkPruneService,
    ChunkPruneTaskNotFound,
    ChunkPruneValidationError,
    region_relpath_for_event,
    seconds_to_ticks,
)
from app.mcmap.events import (
    MCMapChunksPrunedEvent,
    MCMapPruneResultEvent,
    MCMapPrunedChunk,
)
from app.minecraft import MCServerStatus
from app.routers.servers import chunk_prune as chunk_prune_router
from app.world.locks import ServerOperationLock


def _normalize_ring(ring):
    rotations = [ring[i:] + ring[:i] for i in range(len(ring))]
    return min(rotations)


class _FakeInstance:
    def __init__(self, data_path):
        self._data_path = data_path

    def get_data_path(self):
        return self._data_path

    async def exists(self) -> bool:
        return True

    async def get_status(self) -> MCServerStatus:
        return MCServerStatus.EXISTS


class _FakeDocker:
    def __init__(self, data_path):
        self._instance = _FakeInstance(data_path)

    def get_instance(self, server_id):
        return self._instance


def test_seconds_to_ticks():
    assert seconds_to_ticks(0) == 0
    assert seconds_to_ticks(60) == 1200


def test_region_relpath_for_event_accepts_relative_and_absolute_paths(tmp_path):
    data_path = tmp_path / "server"
    region_file = data_path / "world" / "DIM-1" / "region" / "r.-1.2.mca"

    assert (
        region_relpath_for_event(data_path, "world/DIM-1/region/r.-1.2.mca")
        == "world/DIM-1/region"
    )
    assert (
        region_relpath_for_event(data_path, str(region_file))
        == "world/DIM-1/region"
    )
    assert region_relpath_for_event(data_path, "world/entities/r.-1.2.mca") is None
    assert region_relpath_for_event(data_path, "../world/region/r.0.0.mca") is None
    assert region_relpath_for_event(data_path, "/outside/world/region/r.0.0.mca") is None


async def test_preview_collects_chunks_pruned_region_event(tmp_path, monkeypatch):
    service = ChunkPruneService(
        docker=_FakeDocker(tmp_path),  # type: ignore[arg-type]
        operation_lock=ServerOperationLock(),
    )
    metadata = ChunkPruneTaskMetadata(
        task_id="chunk-prune-preview-collect",
        server_id="srv1",
        operation="preview",
        data_path=tmp_path,
        threshold_seconds=60,
        threshold_ticks=1200,
        mode="chunks",
    )

    class _FakeProc:
        returncode = 0

        async def events(self, adapter):
            yield MCMapChunksPrunedEvent(
                type="chunks_pruned",
                region="world/region/r.0.0.mca",
                region_x=0,
                region_z=0,
                chunks=[
                    MCMapPrunedChunk(
                        chunk_x=4,
                        chunk_z=15,
                        rel_x=4,
                        rel_z=15,
                        inhabited_time=480,
                    ),
                    MCMapPrunedChunk(
                        chunk_x=5,
                        chunk_z=15,
                        rel_x=5,
                        rel_z=15,
                        inhabited_time=481,
                    ),
                ],
                dry_run=True,
            )
            yield MCMapPruneResultEvent(
                type="result",
                mode="chunks",
                dry_run=True,
                region_dirs=1,
                regions_scanned=1,
                chunks_scanned=2,
                chunks_selected=2,
                regions_selected=1,
            )

        async def terminate(self):
            return None

        async def stderr(self):
            return ""

    @asynccontextmanager
    async def fake_prune_inhabited(**kwargs):
        yield _FakeProc()

    async def no_claims_file(server_id, data_path):
        return None

    monkeypatch.setattr(
        "app.chunk_prune.service.mcmap_runner.prune_inhabited",
        fake_prune_inhabited,
    )
    monkeypatch.setattr(service, "_write_claims_file", no_claims_file)

    progress = [
        item async for item in service._run_prune_task(metadata, dry_run=True)
    ]

    assert progress[-1].result is not None
    assert progress[-1].result["affected_region_counts_by_dimension"] == {
        "world/region": 1
    }
    assert "dimensions" not in progress[-1].result
    assert metadata.geometry is not None
    assert metadata.geometry.mode == "chunks"
    assert metadata.geometry.threshold_seconds == 60
    assert len(metadata.geometry.dimensions) == 1
    dimension = metadata.geometry.dimensions[0]
    assert dimension.region_dir_relpath == "world/region"
    assert dimension.unit == "chunk"
    assert dimension.cell_count == 2
    assert len(dimension.shapes) == 1
    shape = dimension.shapes[0]
    assert shape.cell_count == 2
    assert shape.bbox == (4, 15, 5, 15)
    assert [_normalize_ring(ring) for ring in shape.rings] == [
        _normalize_ring([(6, 15), (4, 15), (4, 16), (6, 16)])
    ]


async def test_apply_requires_completed_preview(tmp_path):
    service = ChunkPruneService(
        docker=_FakeDocker(tmp_path),  # type: ignore[arg-type]
        operation_lock=ServerOperationLock(),
    )
    task_id = "chunk-prune-preview-test"
    region_dir = tmp_path / "world" / "region"
    region_dir.mkdir(parents=True)
    service._metadata[task_id] = ChunkPruneTaskMetadata(
        task_id=task_id,
        server_id="srv1",
        operation="preview",
        data_path=tmp_path,
        threshold_seconds=60,
        threshold_ticks=1200,
        mode="chunks",
        result={"chunks_selected": 1},
    )

    with pytest.raises(ChunkPruneValidationError):
        await service.start_apply(server_id="srv1", preview_task_id=task_id)


async def test_apply_rejects_missing_preview():
    service = ChunkPruneService(
        docker=_FakeDocker("."),  # type: ignore[arg-type]
        operation_lock=ServerOperationLock(),
    )
    with pytest.raises(ChunkPruneTaskNotFound):
        await service.start_apply(server_id="srv1", preview_task_id="missing")


async def test_task_manager_accepts_stable_task_id():
    async def task_gen():
        yield TaskProgress(progress=100, message="done")

    task_id = "stable-task-id-for-chunk-prune-test"
    task_manager.remove_task(task_id)
    submit = task_manager.submit(
        TaskType.CHUNK_PRUNE_PREVIEW,
        "test",
        task_gen(),
        task_id=task_id,
    )
    assert submit.task.task_id == task_id
    await submit.awaitable
    found_task = task_manager.get_task(task_id)
    assert found_task is not None
    assert found_task.status == TaskStatus.COMPLETED
    assert task_manager.remove_task(task_id)


async def test_chunk_prune_state_returns_latest_preview_and_matching_apply(
    monkeypatch,
):
    async def task_gen():
        yield TaskProgress(progress=100, message="done")

    task_ids = [
        "chunk-prune-state-preview-old",
        "chunk-prune-state-apply-old",
        "chunk-prune-state-preview-new",
        "chunk-prune-state-apply-new",
    ]
    for task_id in task_ids:
        task_manager.remove_task(task_id)

    class _StateInstance:
        async def exists(self):
            return True

    class _StateDocker:
        def get_instance(self, server_id):
            return _StateInstance()

    monkeypatch.setattr(chunk_prune_router, "docker_mc_manager", _StateDocker())

    submissions = []
    try:
        old_preview = task_manager.submit(
            TaskType.CHUNK_PRUNE_PREVIEW,
            "old preview",
            task_gen(),
            server_id="srv1",
            task_id=task_ids[0],
        ).task
        old_apply = task_manager.submit(
            TaskType.CHUNK_PRUNE_APPLY,
            "old apply",
            task_gen(),
            server_id="srv1",
            task_id=task_ids[1],
        ).task
        new_preview = task_manager.submit(
            TaskType.CHUNK_PRUNE_PREVIEW,
            "new preview",
            task_gen(),
            server_id="srv1",
            task_id=task_ids[2],
        ).task
        new_apply = task_manager.submit(
            TaskType.CHUNK_PRUNE_APPLY,
            "new apply",
            task_gen(),
            server_id="srv1",
            task_id=task_ids[3],
        ).task
        submissions = [
            future
            for task_id in task_ids
            if (future := task_manager.get_future(task_id)) is not None
        ]

        old_apply.created_at = old_preview.created_at + timedelta(seconds=1)
        new_preview.created_at = old_apply.created_at + timedelta(seconds=1)
        new_apply.created_at = new_preview.created_at + timedelta(seconds=1)

        state = await chunk_prune_router.get_chunk_prune_state("srv1")

        assert state.preview_task is not None
        assert state.preview_task.task_id == new_preview.task_id
        assert state.apply_task is not None
        assert state.apply_task.task_id == new_apply.task_id
    finally:
        for future in submissions:
            await future
        for task_id in task_ids:
            task_manager.remove_task(task_id)


async def test_chunk_prune_state_hides_apply_before_latest_preview(monkeypatch):
    async def task_gen():
        yield TaskProgress(progress=100, message="done")

    task_ids = [
        "chunk-prune-state-stale-apply",
        "chunk-prune-state-new-preview",
    ]
    for task_id in task_ids:
        task_manager.remove_task(task_id)

    class _StateInstance:
        async def exists(self):
            return True

    class _StateDocker:
        def get_instance(self, server_id):
            return _StateInstance()

    monkeypatch.setattr(chunk_prune_router, "docker_mc_manager", _StateDocker())

    submissions = []
    try:
        stale_apply = task_manager.submit(
            TaskType.CHUNK_PRUNE_APPLY,
            "stale apply",
            task_gen(),
            server_id="srv1",
            task_id=task_ids[0],
        ).task
        new_preview = task_manager.submit(
            TaskType.CHUNK_PRUNE_PREVIEW,
            "new preview",
            task_gen(),
            server_id="srv1",
            task_id=task_ids[1],
        ).task
        submissions = [
            future
            for task_id in task_ids
            if (future := task_manager.get_future(task_id)) is not None
        ]

        new_preview.created_at = stale_apply.created_at + timedelta(seconds=1)

        state = await chunk_prune_router.get_chunk_prune_state("srv1")

        assert state.preview_task is not None
        assert state.preview_task.task_id == new_preview.task_id
        assert state.apply_task is None
    finally:
        for future in submissions:
            await future
        for task_id in task_ids:
            task_manager.remove_task(task_id)


async def test_chunk_prune_geometry_endpoint_returns_completed_preview_geometry(
    tmp_path, monkeypatch
):
    service = ChunkPruneService(
        docker=_FakeDocker(tmp_path),  # type: ignore[arg-type]
        operation_lock=ServerOperationLock(),
    )
    task_id = "chunk-prune-geometry-completed"
    task_manager.remove_task(task_id)

    async def task_gen():
        yield TaskProgress(progress=100, message="done", result={"dry_run": True})

    submit = task_manager.submit(
        TaskType.CHUNK_PRUNE_PREVIEW,
        "preview",
        task_gen(),
        server_id="srv1",
        task_id=task_id,
    )
    service._metadata[task_id] = ChunkPruneTaskMetadata(
        task_id=task_id,
        server_id="srv1",
        operation="preview",
        data_path=tmp_path,
        threshold_seconds=30,
        threshold_ticks=600,
        mode="regions",
        result={"dry_run": True},
        geometry=ChunkPrunePreviewGeometryResponse(
            task_id=task_id,
            server_id="srv1",
            mode="regions",
            threshold_seconds=30,
            threshold_ticks=600,
            dimensions=[],
        ),
    )
    monkeypatch.setattr(chunk_prune_router, "chunk_prune_service", service)

    try:
        await submit.awaitable
        response = await chunk_prune_router.get_chunk_prune_preview_geometry(
            "srv1",
            task_id,
        )

        assert response.task_id == task_id
        assert response.mode == "regions"
        assert response.dimensions == []
    finally:
        task_manager.remove_task(task_id)
