import asyncio

import pytest
from fastapi import HTTPException

from app.operation_admission import ServerWriteAdmission
from app.operations.coordinator import (
    ConflictPolicy,
    OperationCoordinator,
    ResourceClaim,
    ResourceKind,
    ResourceLease,
)


async def test_cross_category_acquisition_is_atomic_and_unrelated_work_continues():
    coordinator = OperationCoordinator(ServerWriteAdmission())
    ports = ResourceClaim(ResourceKind.PORT_ALLOCATION)
    first = ResourceClaim(ResourceKind.MAINTENANCE, "first")
    second = ResourceClaim(ResourceKind.MAINTENANCE, "second")
    async with coordinator.acquire([first]):
        async with coordinator.acquire([first, ports], policy=ConflictPolicy.SKIP) as skipped:
            assert skipped is None
            assert not coordinator.is_occupied(ports)
        async with coordinator.acquire([second, ports]) as lease:
            assert lease is not None
            assert lease.claims == (ports, second)


async def test_nested_safety_backup_requires_live_covering_lease():
    coordinator = OperationCoordinator(ServerWriteAdmission())
    world = ResourceClaim(ResourceKind.FILES, "first", "world")
    region = ResourceClaim(ResourceKind.FILES, "first", "world/region")
    elsewhere = ResourceClaim(ResourceKind.FILES, "other", "world")
    async with coordinator.acquire([world]) as lease:
        assert lease is not None
        async with coordinator.acquire([region], parent=lease) as nested:
            assert nested is lease
        with pytest.raises(RuntimeError, match="expand"):
            async with coordinator.acquire([elsewhere], parent=lease):
                pytest.fail("A nested backup expanded its resource scope")
        forged = ResourceLease(lease.claims, lease.owner)
        with pytest.raises(RuntimeError, match="no longer active"), coordinator.reuse(forged, [region]):
            pytest.fail("A copied lease was accepted")
    with pytest.raises(RuntimeError, match="no longer active"), coordinator.reuse(lease, [region]):
        pytest.fail("An expired backup lease was accepted")


async def test_delete_freezes_queue_without_holding_its_execution_resources():
    admission = ServerWriteAdmission()
    coordinator = OperationCoordinator(admission)
    claim = ResourceClaim(ResourceKind.MAINTENANCE, "first")
    queued = asyncio.Event()

    async def waiting_writer():
        queued.set()
        async with coordinator.acquire([claim]):
            pytest.fail("A cancelled queued writer started")

    async with coordinator.acquire([claim]):
        worker = asyncio.create_task(waiting_writer())
        await queued.wait()
        with admission.freeze("first") as permit:
            with pytest.raises(HTTPException):
                async with coordinator.delete("first", permit):
                    pytest.fail("Deletion overlapped the active writer")
            worker.cancel()
            with pytest.raises(asyncio.CancelledError):
                await worker
            with pytest.raises(HTTPException):
                admission.check("first")
    with admission.freeze("first") as permit:
        async with coordinator.delete("first", permit):
            assert coordinator.is_occupied(claim)
            with pytest.raises(HTTPException), admission.write(["first"]):
                pytest.fail("A writer entered during deletion")
    admission.require_drained("first")


async def test_file_scopes_conflict_only_for_overlapping_paths():
    coordinator = OperationCoordinator(ServerWriteAdmission())
    async with (
        coordinator.acquire([ResourceClaim(ResourceKind.FILES, "first", "world")]),
        coordinator.acquire([ResourceClaim(ResourceKind.FILES, "first", "plugins")]),
    ):
        with pytest.raises(HTTPException):
            async with coordinator.acquire(
                [ResourceClaim(ResourceKind.FILES, "first", "world/region")], policy=ConflictPolicy.REJECT,
            ):
                pytest.fail("Overlapping world writes ran concurrently")
