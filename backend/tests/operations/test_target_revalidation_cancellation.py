import asyncio
from collections.abc import AsyncGenerator

import aiosqlite
import anyio
import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.background_tasks.manager import BackgroundTaskManager
from app.background_tasks.types import TaskProgress, TaskStatus, TaskType
from app.db.metadata import Base
from app.operations.context import (
    OperationExecution,
    bind_execution,
    revalidate_targets,
)
from app.operations.coordinator import (
    ResourceClaim,
    ResourceKind,
    get_operation_coordinator,
)
from app.operations.journal import OperationJournal
from app.operations.journal_types import OperationState
from app.runtime_resources import current_runtime
from app.servers.models import Server
from app.servers.references import resolve_server_ref
from tests.support.runtime import set_runtime_resource


@pytest.fixture
async def revalidation_database(tmp_path, monkeypatch) -> AsyncGenerator[AsyncEngine]:
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'revalidation.sqlite3'}",
        connect_args={"timeout": 0.1},
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    set_runtime_resource(monkeypatch, "session_factory", sessions)
    project = current_runtime().settings.server_path / "survival"
    (project / "data").mkdir(parents=True)
    (project / "compose.yml").write_text("services: {}\n")
    async with sessions.begin() as session:
        session.add(Server(server_id="survival"))
    try:
        yield engine
    finally:
        await engine.dispose()


async def target_execution(engine: AsyncEngine) -> OperationExecution:
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions() as session:
        reference = await resolve_server_ref(session, "survival", servers_root=current_runtime().settings.server_path)
    return OperationExecution(OperationJournal(sessions), "revalidate", (reference,))


async def verify_independent_writer(engine: AsyncEngine) -> None:
    independent = create_async_engine(engine.url, connect_args={"timeout": 0.1})
    try:
        async with independent.begin() as connection:
            await connection.execute(text("UPDATE server SET server_id = server_id"))
    finally:
        await independent.dispose()


@pytest.mark.parametrize("validation", ["task_start", "lease_acquisition"])
async def test_cancelled_target_read_settles_durable_task_without_leaking_sqlite_reader(
    revalidation_database: AsyncEngine, monkeypatch, validation: str,
):
    journal = OperationJournal(async_sessionmaker(revalidation_database, expire_on_commit=False))
    manager = BackgroundTaskManager(journal)
    coordinator = get_operation_coordinator()
    claim = ResourceClaim(ResourceKind.FILES, "survival", "data")
    acquired, release = asyncio.Event(), asyncio.Event()
    execute = aiosqlite.Connection._execute
    armed = False
    reads = 0
    executed = False

    async def hold_target_result(connection, function, *args, **kwargs):
        nonlocal reads
        result = await execute(connection, function, *args, **kwargs)
        if armed and args and isinstance(args[0], str) and args[0].startswith("SELECT server.id, server.status"):
            reads += 1
            if reads == (1 if validation == "task_start" else 2):
                acquired.set()
                await release.wait()
        return result

    monkeypatch.setattr(aiosqlite.Connection, "_execute", hold_target_result)

    async def operation():
        nonlocal executed
        async with coordinator.acquire([claim]):
            executed = True
            yield TaskProgress(progress=100)

    try:
        submitted = await manager.submit_durable(
            TaskType.ARCHIVE_CREATE, "cancel target validation", operation(), server_id="survival", claims=[claim],
        )
        armed = True
        await asyncio.wait_for(acquired.wait(), 2)
        assert await manager.cancel(submitted.task_id)
        release.set()
        result = await asyncio.wait_for(submitted.awaitable, 2)
        assert not result.success
        assert submitted.task.status == TaskStatus.CANCELLED
        assert not executed
        assert not coordinator.is_occupied(claim)
        record = await journal.get(submitted.task_id)
        assert record is not None and record.state == OperationState.CANCELLED
        assert record.writers_stopped and not record.processes
        assert await journal.unsettled() == []
        await verify_independent_writer(revalidation_database)
    finally:
        release.set()
        await manager.shutdown()


@pytest.mark.parametrize("cancellation", ["anyio", "asyncio"])
async def test_cancelled_target_cursor_closes_before_releasing_lease(
    revalidation_database: AsyncEngine, monkeypatch, cancellation: str,
):
    execution = await target_execution(revalidation_database)
    coordinator = get_operation_coordinator()
    claim = ResourceClaim(ResourceKind.FILES, "survival", "data")
    acquired, release = asyncio.Event(), asyncio.Event()
    execute = aiosqlite.Connection._execute
    failures: list[BaseException] = []
    executed = False

    async def hold_target_result(connection, function, *args, **kwargs):
        result = await execute(connection, function, *args, **kwargs)
        if args and isinstance(args[0], str) and args[0].startswith("SELECT server.id, server.status"):
            acquired.set()
            await release.wait()
        return result

    monkeypatch.setattr(aiosqlite.Connection, "_execute", hold_target_result)

    async def operation():
        nonlocal executed
        with bind_execution(execution):
            try:
                async with coordinator.acquire([claim]):
                    executed = True
            except BaseException as error:
                failures.append(error)
                raise

    if cancellation == "anyio":
        async with anyio.create_task_group() as group:
            group.start_soon(operation)
            try:
                await asyncio.wait_for(acquired.wait(), 2)
                group.cancel_scope.cancel()
            finally:
                release.set()
    else:
        worker = asyncio.create_task(operation())
        try:
            await asyncio.wait_for(acquired.wait(), 2)
            worker.cancel()
            release.set()
            with pytest.raises(asyncio.CancelledError):
                await worker
        finally:
            release.set()
            await asyncio.gather(worker, return_exceptions=True)

    assert not executed
    assert len(failures) == 1 and isinstance(failures[0], asyncio.CancelledError)
    assert not coordinator.is_occupied(claim)
    await verify_independent_writer(revalidation_database)


@pytest.mark.parametrize("cancellation", ["anyio", "asyncio"])
@pytest.mark.parametrize("close_failure", [False, True])
async def test_target_session_close_settles_before_cancellation_and_lease_release(
    revalidation_database: AsyncEngine, monkeypatch, cancellation: str, close_failure: bool,
):
    execution = await target_execution(revalidation_database)
    coordinator = get_operation_coordinator()
    claim = ResourceClaim(ResourceKind.FILES, "survival", "data")
    closing, release = asyncio.Event(), asyncio.Event()
    failures: list[BaseException] = []
    executed = False
    closed = False

    class SlowClose(AsyncSession):
        async def close(self) -> None:
            nonlocal closed
            closing.set()
            await release.wait()
            await super().close()
            closed = True
            if close_failure:
                raise OSError("synthetic target session close failure")

    sessions = async_sessionmaker(revalidation_database, class_=SlowClose, expire_on_commit=False)
    set_runtime_resource(monkeypatch, "session_factory", sessions)

    async def operation():
        nonlocal executed
        with bind_execution(execution):
            try:
                async with coordinator.acquire([claim]):
                    executed = True
            except BaseException as error:
                assert closed
                failures.append(error)
                raise

    if cancellation == "anyio":
        async with anyio.create_task_group() as group:
            group.start_soon(operation)
            try:
                await asyncio.wait_for(closing.wait(), 2)
                group.cancel_scope.cancel()
                assert coordinator.is_occupied(claim)
            finally:
                release.set()
    else:
        worker = asyncio.create_task(operation())
        try:
            await asyncio.wait_for(closing.wait(), 2)
            for _ in range(2):
                worker.cancel("cancel during target session close")
                advanced = asyncio.Event()
                asyncio.get_running_loop().call_soon(advanced.set)
                await advanced.wait()
                assert not worker.done() and not closed
                assert coordinator.is_occupied(claim)
            release.set()
            with pytest.raises(asyncio.CancelledError, match="cancel during target session close"):
                await worker
        finally:
            release.set()
            await asyncio.gather(worker, return_exceptions=True)

    assert not executed and closed
    assert len(failures) == 1 and isinstance(failures[0], asyncio.CancelledError)
    if close_failure:
        assert isinstance(failures[0].__cause__, OSError)
        assert str(failures[0].__cause__) == "synthetic target session close failure"
    assert not coordinator.is_occupied(claim)
    await verify_independent_writer(revalidation_database)


async def test_already_cancelled_revalidation_does_not_open_a_session(revalidation_database: AsyncEngine, monkeypatch):
    execution = await target_execution(revalidation_database)
    opened = False

    def forbidden_session():
        nonlocal opened
        opened = True
        raise AssertionError("cancelled revalidation opened a session")

    set_runtime_resource(monkeypatch, "session_factory", forbidden_session)
    with bind_execution(execution), anyio.CancelScope() as scope:
        scope.cancel()
        await revalidate_targets()
        pytest.fail("cancelled revalidation returned to external work")
    assert scope.cancelled_caught and not opened


async def test_failed_revalidation_preserves_conflict_and_closes_session(revalidation_database: AsyncEngine, monkeypatch):
    execution = await target_execution(revalidation_database)
    async with revalidation_database.begin() as connection:
        await connection.execute(text("UPDATE server SET status = 'REMOVED'"))
    closed = False

    class ObservedClose(AsyncSession):
        async def close(self) -> None:
            nonlocal closed
            await super().close()
            closed = True

    set_runtime_resource(monkeypatch, "session_factory", async_sessionmaker(revalidation_database, class_=ObservedClose, expire_on_commit=False))
    with bind_execution(execution), pytest.raises(HTTPException) as failure:
        await revalidate_targets()
    assert failure.value.status_code == 409
    assert "服务器实例已停用" in failure.value.detail
    assert closed
    await verify_independent_writer(revalidation_database)
