from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.minecraft import MCServerStatus
from app.routers.servers import operations
from app.snapshots.restore import SnapshotRestoreService, SnapshotServerRunning
from app.world.locks import LockHolder, ServerOperationKind, ServerOperationLock
from app.world.maintenance import affected_servers


class Instance:
    def __init__(self, project, name):
        self.project = project
        self.name = name
        self.status = MCServerStatus.RUNNING
        self.start = AsyncMock()
        self.up = AsyncMock()
        self.restart = AsyncMock()

    def get_project_path(self):
        return self.project

    def get_data_path(self):
        return self.project / "data"

    def get_name(self):
        return self.name

    async def get_status(self):
        return self.status

    async def exists(self):
        return True


@pytest.fixture
def manager(tmp_path):
    instances = [Instance(tmp_path / name, name) for name in ("one", "two")]
    for instance in instances:
        world = instance.get_data_path() / "world"
        (world / "region").mkdir(parents=True)
        (world / "level.dat").touch()
    return SimpleNamespace(
        get_all_instances=AsyncMock(return_value=instances),
        get_instance=lambda name: next(i for i in instances if i.name == name),
    )


async def test_snapshot_targets_distinguish_online_files_and_worlds(manager, tmp_path):
    one = manager.get_instance("one")
    data = one.get_data_path()
    assert (
        await affected_servers(manager, [data / "server.properties"], world_only=True)
        == []
    )
    assert (
        await affected_servers(
            manager, [data / "plugins" / "settings.yml"], world_only=True
        )
        == []
    )
    assert await affected_servers(
        manager, [data / "world" / "region" / "r.0.0.mca"], world_only=True
    ) == ["one"]
    assert await affected_servers(manager, [data], world_only=True) == ["one"]
    assert await affected_servers(manager, [tmp_path], world_only=True) == [
        "one",
        "two",
    ]
    service = SnapshotRestoreService(Mock(), manager, ServerOperationLock())
    await service.check_available(
        await service.maintenance_servers([data / "server.properties"])
    )
    with pytest.raises(SnapshotServerRunning):
        await service.check_available(await service.maintenance_servers([data]))


@pytest.mark.parametrize("action", ["start", "up", "restart"])
async def test_server_cannot_start_during_world_maintenance(
    manager, monkeypatch, action
):
    lock = ServerOperationLock()
    monkeypatch.setattr(operations, "docker_mc_manager", manager)
    monkeypatch.setattr(operations, "server_operation_lock", lock)
    holder = LockHolder(ServerOperationKind.PRUNE, datetime.now(UTC), None, "pruning")
    async with lock.acquire("one", holder):
        status = await operations.server_maintenance("one", Mock())
        assert status["active"]
        with pytest.raises(operations.HTTPException) as error:
            await operations.server_operation(
                "one",
                operations.ServerOperation(action=action),
                AsyncMock(),
                Mock(id=1),
            )
        assert error.value.status_code == 423
    assert not (await operations.server_maintenance("one", Mock()))["active"]
    getattr(manager.get_instance("one"), action).assert_not_awaited()
    await operations.server_operation(
        "one", operations.ServerOperation(action=action), AsyncMock(), Mock(id=1)
    )
    getattr(manager.get_instance("one"), action).assert_awaited_once()


async def test_broken_unrelated_properties_do_not_block_file_recovery(manager):
    from app.minecraft.properties import read_level_name

    data = manager.get_instance("one").get_data_path()
    (data / "server.properties").write_text(
        "server-port=invalid\nlevel-name=custom\nlevel-name=last\nlevel-name=\n"
    )
    assert await read_level_name(data) == "last"
    assert (
        await affected_servers(manager, [data / "server.properties"], world_only=True)
        == []
    )
    assert await affected_servers(
        manager, [data / "last" / "region" / "r.0.0.mca"], world_only=True
    ) == ["one"]
    (data / "server.properties").write_text("server-port=invalid\n")
    assert await read_level_name(data) == "world"
