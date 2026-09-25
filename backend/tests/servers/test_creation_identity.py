import asyncio
import threading
from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock

import pytest
import yaml
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.metadata import Base
from app.errors import PublicOperationError
from app.minecraft import DockerMCManager, MCInstance
from app.minecraft.docker.manager import ComposeManager
from app.operation_admission import ServerWriteAdmission
from app.operations.coordinator import OperationCoordinator, ResourceClaim, ResourceKind
from app.servers import port_utils
from app.servers.crud import create_server_record, mark_server_removed
from app.servers.lifecycle import (
    CreateServerSpec,
    adopt_server_partial,
    create_server_full,
    orchestrators,
)
from app.servers.models import Server, ServerStatus
from app.servers.references import resolve_server_ref
from tests.fixtures.test_utils import create_mc_server_compose_yaml
from tests.support.runtime import set_runtime_resource


def compose(server_id: str, game_port: int, rcon_port: int) -> str:
    content = yaml.safe_load(create_mc_server_compose_yaml(server_id, game_port, rcon_port))
    content["services"]["mc"]["environment"]["SERVER_PORT"] = "25565"
    return yaml.safe_dump(content)


@pytest.fixture
async def creation_environment(tmp_path, monkeypatch):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'creation.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    root = tmp_path / "identity-servers"
    root.mkdir()
    manager = DockerMCManager(root)
    set_runtime_resource(monkeypatch, "docker_mc_manager", manager)
    set_runtime_resource(monkeypatch, 'operation_coordinator', OperationCoordinator(ServerWriteAdmission()))
    monkeypatch.setattr(orchestrators.get_log_monitor(), "start_server", AsyncMock())
    monkeypatch.setattr(orchestrators.get_log_monitor(), "stop_watching", AsyncMock())
    monkeypatch.setattr(orchestrators.get_dns_manager(), "update", AsyncMock())
    monkeypatch.setattr(port_utils, "get_system_used_ports", Mock(return_value=set()))
    monkeypatch.setattr(ComposeManager, "created", AsyncMock(return_value=False))
    yield sessions, manager
    await engine.dispose()


@pytest.mark.parametrize("second_name", ["first", "second"])
async def test_concurrent_creation_reserves_name_and_ports_through_database_write(
    creation_environment, monkeypatch, second_name,
):
    sessions, manager = creation_environment
    entered = asyncio.Event()
    release = asyncio.Event()
    second_started = asyncio.Event()
    checks = 0
    real_check = orchestrators.check_port_conflicts

    async def check_ports(*args, **kwargs):
        nonlocal checks
        checks += 1
        if checks == 1:
            entered.set()
            await release.wait()
        return await real_check(*args, **kwargs)

    monkeypatch.setattr(orchestrators, "check_port_conflicts", check_ports)

    async def create(name):
        async with sessions() as session:
            if name == second_name and asyncio.current_task() is second:
                second_started.set()
            return await create_server_full(
                session, name,
                CreateServerSpec(yaml_content=compose(name, 35140, 35141)),
            )

    second = None
    first = asyncio.create_task(create("first"))
    await asyncio.wait_for(entered.wait(), 2)
    second = asyncio.create_task(create(second_name))
    try:
        await asyncio.wait_for(second_started.wait(), 2)
        assert checks == 1
        assert not second.done()
    finally:
        release.set()
    await asyncio.wait_for(first, 2)
    with pytest.raises(HTTPException) as conflict:
        await asyncio.wait_for(second, 2)
    assert conflict.value.status_code == 409
    async with sessions() as session:
        rows = (await session.execute(select(Server).where(Server.status == ServerStatus.ACTIVE))).scalars().all()
        assert [row.server_id for row in rows] == ["first"]
    assert await manager.get_instance("first").exists()
    if second_name != "first":
        assert not manager.get_instance(second_name).get_project_path().exists()


async def test_explicit_adoption_creates_new_generation_and_retains_history(creation_environment):
    sessions, manager = creation_environment
    instance = manager.get_instance("legacy")
    await instance.create(create_mc_server_compose_yaml("legacy", 35150, 35151))
    async with sessions() as session:
        old = await create_server_record(session, "legacy")
        await mark_server_removed(session, "legacy", datetime.now(UTC))
        with pytest.raises(HTTPException) as inactive:
            await resolve_server_ref(session, "legacy", servers_root=manager.servers_path)
        assert inactive.value.status_code == 409
        await adopt_server_partial(session, "legacy", game_port=35150, rcon_port=35151)
        current = await resolve_server_ref(session, "legacy", servers_root=manager.servers_path)
        assert current.generation > old.id
        rows = (await session.execute(select(Server).order_by(Server.id))).scalars().all()
        assert [(row.id, row.status) for row in rows] == [(old.id, ServerStatus.REMOVED), (current.generation, ServerStatus.ACTIVE)]


async def test_adoption_rejects_changed_preview_and_does_not_create_record(creation_environment):
    sessions, manager = creation_environment
    await manager.get_instance("legacy").create(create_mc_server_compose_yaml("legacy", 35160, 35161))
    async with sessions() as session:
        with pytest.raises(HTTPException) as changed:
            await adopt_server_partial(session, "legacy", game_port=35162, rcon_port=35163)
        assert changed.value.status_code == 409
        assert (await session.execute(select(Server))).scalars().all() == []


async def test_active_record_with_missing_directory_is_not_recreated(creation_environment):
    sessions, manager = creation_environment
    async with sessions() as session:
        original = await create_server_record(session, "missing")
        with pytest.raises(HTTPException) as conflict:
            await create_server_full(
                session, "missing", CreateServerSpec(yaml_content=create_mc_server_compose_yaml("missing", 35170, 35171))
            )
        assert conflict.value.status_code == 409
        assert (await session.execute(select(Server.id))).scalars().all() == [original.id]
    assert not manager.get_instance("missing").get_project_path().exists()


async def test_existing_unregistered_directory_is_never_owned_by_failed_creation(creation_environment):
    sessions, manager = creation_environment
    project = manager.get_instance("legacy-data").get_project_path()
    project.mkdir()
    original = project / "keep.txt"
    original.write_text("existing user data")
    async with sessions() as session:
        with pytest.raises(HTTPException) as conflict:
            await create_server_full(session, "legacy-data", CreateServerSpec(yaml_content=compose("legacy-data", 35180, 35181)))
        assert conflict.value.status_code == 409
        assert (await session.execute(select(Server))).scalars().all() == []
    assert original.read_text() == "existing user data"


async def test_cancelled_generator_waits_for_io_before_removing_created_directory(creation_environment, monkeypatch):
    sessions, manager = creation_environment
    writer_started = asyncio.Event()
    release_writer = threading.Event()
    loop = asyncio.get_running_loop()
    project = manager.get_instance("cancel-io").get_project_path()

    def write_tree():
        project.mkdir()
        loop.call_soon_threadsafe(writer_started.set)
        assert release_writer.wait(timeout=5)
        (project / "late-write.txt").write_text("owned by the cancelled creation")

    async def delayed_create(_self, _yaml):
        await asyncio.to_thread(write_tree)

    monkeypatch.setattr(MCInstance, "create", delayed_create)

    async def generator():
        async with sessions() as session:
            await create_server_full(session, "cancel-io", CreateServerSpec(yaml_content=compose("cancel-io", 35190, 35191)))
            yield "completed"

    stream = generator()
    operation = asyncio.create_task(anext(stream))
    try:
        await asyncio.wait_for(writer_started.wait(), 2)
        operation.cancel()
        await asyncio.sleep(0)
        assert not operation.done()
        assert project.is_dir()
    finally:
        release_writer.set()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(operation, 3)
    await stream.aclose()
    assert not project.exists()
    async with sessions() as session:
        assert (await session.execute(select(Server.status))).scalars().all() == [ServerStatus.REMOVED]


async def test_repeated_cancellation_cannot_release_port_lease_before_cleanup(creation_environment, monkeypatch):
    sessions, manager = creation_environment
    started = asyncio.Event()
    cleanup_started = asyncio.Event()
    release_cleanup = asyncio.Event()
    original_remove = MCInstance.remove

    async def hold_monitor(_server_id):
        started.set()
        await asyncio.Event().wait()

    async def hold_remove(instance):
        cleanup_started.set()
        await release_cleanup.wait()
        await original_remove(instance)

    monkeypatch.setattr(orchestrators.get_log_monitor(), "start_server", hold_monitor)
    monkeypatch.setattr(MCInstance, "remove", hold_remove)

    async def create():
        async with sessions() as session:
            await create_server_full(session, "cancel-cleanup", CreateServerSpec(yaml_content=compose("cancel-cleanup", 35200, 35201)))

    operation = asyncio.create_task(create())
    await asyncio.wait_for(started.wait(), 2)
    operation.cancel()
    await asyncio.wait_for(cleanup_started.wait(), 2)
    operation.cancel()
    await asyncio.sleep(0)
    try:
        assert not operation.done()
        assert orchestrators.get_operation_coordinator().is_occupied(ResourceClaim(ResourceKind.PORT_ALLOCATION))
    finally:
        release_cleanup.set()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(operation, 2)
    assert not manager.get_instance("cancel-cleanup").get_project_path().exists()
    assert not orchestrators.get_operation_coordinator().is_occupied(ResourceClaim(ResourceKind.PORT_ALLOCATION))


async def test_failed_cleanup_reports_residual_directory_without_secret(creation_environment, monkeypatch, caplog):
    sessions, manager = creation_environment
    secret = "synthetic-create-cleanup-password"
    original_record = orchestrators.create_server_record

    async def persist_then_fail(*args, **kwargs):
        await original_record(*args, **kwargs)
        raise RuntimeError(secret)

    monkeypatch.setattr(orchestrators, "create_server_record", persist_then_fail)
    monkeypatch.setattr(MCInstance, "remove", AsyncMock(side_effect=RuntimeError(secret)))
    async with sessions() as session:
        with pytest.raises(PublicOperationError) as incomplete:
            await create_server_full(session, "cleanup-failed", CreateServerSpec(yaml_content=compose("cleanup-failed", 35210, 35211)))
        assert "清理未完成" in str(incomplete.value)
        assert "cleanup-failed" in str(incomplete.value)
        assert (await session.execute(select(Server.status))).scalars().all() == [ServerStatus.REMOVED]
    assert await manager.get_instance("cleanup-failed").exists()
    assert secret not in str(incomplete.value)
    assert secret not in caplog.text
