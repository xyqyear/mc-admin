import asyncio
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from pathlib import Path

import aiosqlite
import anyio
import pytest
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.db.metadata import Base
from app.operations.context import OperationExecution, bind_execution, current_execution
from app.operations.journal import OperationJournal
from app.operations.journal_types import (
    OperationSpec,
    OperationState,
    ResourceReference,
)
from app.runtime_resources import current_runtime


@pytest.fixture
async def cancellation_database(tmp_path: Path) -> AsyncGenerator[AsyncEngine]:
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'journal-cancellation.sqlite3'}",
        connect_args={"timeout": 0.1},
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    try:
        yield engine
    finally:
        await engine.dispose()


async def test_level_cancellation_after_begin_releases_database_writer(cancellation_database: AsyncEngine):
    journal = OperationJournal(async_sessionmaker(cancellation_database, expire_on_commit=False))
    await journal.accept(OperationSpec("world_restore", (ResourceReference("world", "survival", 1),), operation_id="cancel"))
    reached_external_work = False

    with anyio.CancelScope() as scope:
        def cancel_after_begin(_connection, _cursor, statement, _parameters, _context, _many):
            if statement == "BEGIN IMMEDIATE":
                scope.cancel()

        event.listen(cancellation_database.sync_engine, "after_cursor_execute", cancel_after_begin)
        try:
            await journal.start("cancel")
            reached_external_work = True
        finally:
            event.remove(cancellation_database.sync_engine, "after_cursor_execute", cancel_after_begin)

    assert scope.cancelled_caught
    assert not reached_external_work
    independent = create_async_engine(cancellation_database.url, connect_args={"timeout": 0.1})
    try:
        async with independent.begin() as connection:
            await connection.execute(text("UPDATE operation_journal SET phase = 'independent_writer' WHERE operation_id = 'cancel'"))
    finally:
        await independent.dispose()


@pytest.mark.parametrize(("method", "cancel_statement"), [
    ("start", "BEGIN IMMEDIATE"),
    ("start", "SELECT operation_journal"),
    ("get", "SELECT operation_journal"),
])
@pytest.mark.parametrize("cancellation", ["anyio", "asyncio"])
async def test_cancelled_sqlite_call_does_not_leave_cursor_holding_writer_lock(
    cancellation_database: AsyncEngine, monkeypatch, method: str, cancel_statement: str, cancellation: str,
):
    journal = OperationJournal(async_sessionmaker(cancellation_database, expire_on_commit=False))
    await journal.accept(OperationSpec("world_restore", (ResourceReference("world", "survival", 1),), operation_id="cancel"))
    execute = aiosqlite.Connection._execute
    acquired = asyncio.Event()
    release = asyncio.Event()
    reached_external_work = False
    failures: list[BaseException] = []

    async def hold_sql_result(connection, function, *args, **kwargs):
        result = await execute(connection, function, *args, **kwargs)
        if args and isinstance(args[0], str) and args[0].startswith(cancel_statement):
            acquired.set()
            await release.wait()
        return result

    monkeypatch.setattr(aiosqlite.Connection, "_execute", hold_sql_result)

    async def write():
        nonlocal reached_external_work
        try:
            await (journal.start("cancel") if method == "start" else journal.get("cancel"))
            reached_external_work = True
        except BaseException as error:
            # Restore finalization still owns the cancellation traceback while writing its terminal history.
            failures.append(error)
            raise

    if cancellation == "anyio":
        async with anyio.create_task_group() as group:
            group.start_soon(write)
            await acquired.wait()
            group.cancel_scope.cancel()
            release.set()
    else:
        writer = asyncio.create_task(write())
        try:
            await asyncio.wait_for(acquired.wait(), 2)
            writer.cancel()
            release.set()
            with pytest.raises(asyncio.CancelledError):
                await writer
        finally:
            release.set()
            if not writer.done():
                writer.cancel()
                await asyncio.gather(writer, return_exceptions=True)

    assert not reached_external_work
    assert failures
    independent = create_async_engine(cancellation_database.url, connect_args={"timeout": 0.1})
    try:
        async with independent.begin() as connection:
            await connection.execute(text("UPDATE operation_journal SET phase = 'independent_writer' WHERE operation_id = 'cancel'"))
    finally:
        await independent.dispose()


async def test_repeated_cancellation_waits_for_session_close_before_unlocking(cancellation_database: AsyncEngine):
    journal = OperationJournal(async_sessionmaker(cancellation_database, expire_on_commit=False))
    await journal.accept(OperationSpec("world_restore", (ResourceReference("world", "survival", 1),), operation_id="cancel"))
    closing, release = asyncio.Event(), asyncio.Event()

    class SlowClose(AsyncSession):
        async def close(self) -> None:
            closing.set()
            await release.wait()
            await super().close()

    journal.session_factory = async_sessionmaker[AsyncSession](cancellation_database, class_=SlowClose, expire_on_commit=False)
    writer = asyncio.create_task(journal.start("cancel"))
    try:
        await asyncio.wait_for(closing.wait(), 2)
        for _ in range(2):
            writer.cancel()
            advanced = asyncio.Event()
            asyncio.get_running_loop().call_soon(advanced.set)
            await advanced.wait()
            assert not writer.done()
            assert journal._lock.locked()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await writer
    finally:
        release.set()
        await asyncio.gather(writer, return_exceptions=True)

    assert not journal._lock.locked()
    record = await journal.get("cancel")
    assert record is not None and record.state == OperationState.RUNNING


async def test_failed_transaction_rolls_back_and_reports_close_failure(cancellation_database: AsyncEngine):
    class CloseFailure(AsyncSession):
        async def close(self) -> None:
            await super().close()
            raise OSError("synthetic session close failure")

    journal = OperationJournal(async_sessionmaker(cancellation_database, class_=CloseFailure, expire_on_commit=False))
    with pytest.raises(OSError, match="synthetic session close failure") as failure:
        await journal.start("missing-operation")
    assert isinstance(failure.value.__context__, KeyError)
    assert not journal._lock.locked()
    independent = create_async_engine(cancellation_database.url, connect_args={"timeout": 0.1})
    try:
        async with independent.begin() as connection:
            await connection.execute(text("CREATE TABLE independent_writer (value INTEGER)"))
    finally:
        await independent.dispose()


async def test_cancelled_waiting_writer_does_not_change_journal(cancellation_database: AsyncEngine):
    journal = OperationJournal(async_sessionmaker(cancellation_database, expire_on_commit=False))
    await journal.accept(OperationSpec("world_restore", (ResourceReference("world", "survival", 1),), operation_id="waiting"))
    entered = asyncio.Event()

    async def write():
        entered.set()
        await journal.start("waiting")

    async with journal._lock:
        writer = asyncio.create_task(write())
        await entered.wait()
        writer.cancel()
        with pytest.raises(asyncio.CancelledError):
            await writer

    record = await journal.get("waiting")
    assert record is not None and record.state == OperationState.QUEUED


@pytest.mark.parametrize("cancellation", ["anyio", "asyncio"])
async def test_cancelled_close_failure_preserves_cancellation_and_cleanup_cause(
    cancellation_database: AsyncEngine, cancellation: str,
):
    journal = OperationJournal(async_sessionmaker(cancellation_database, expire_on_commit=False))
    await journal.accept(OperationSpec("world_restore", (ResourceReference("world", "survival", 1),), operation_id="cancel"))
    closing, release = asyncio.Event(), asyncio.Event()
    failures: list[BaseException] = []
    reached_external_work = False

    class CloseFailure(AsyncSession):
        async def close(self) -> None:
            closing.set()
            await release.wait()
            await super().close()
            raise OSError("synthetic cancelled close failure")

    journal.session_factory = async_sessionmaker[AsyncSession](cancellation_database, class_=CloseFailure, expire_on_commit=False)

    async def write():
        nonlocal reached_external_work
        try:
            await journal.start("cancel")
            reached_external_work = True
        except BaseException as error:
            failures.append(error)
            raise

    if cancellation == "anyio":
        async with anyio.create_task_group() as group:
            group.start_soon(write)
            await closing.wait()
            group.cancel_scope.cancel()
            release.set()
    else:
        writer = asyncio.create_task(write())
        try:
            await asyncio.wait_for(closing.wait(), 2)
            writer.cancel("synthetic disconnect")
            release.set()
            with pytest.raises(asyncio.CancelledError, match="synthetic disconnect"):
                await writer
        finally:
            release.set()
            await asyncio.gather(writer, return_exceptions=True)

    assert not reached_external_work
    assert not journal._lock.locked()
    assert len(failures) == 1 and isinstance(failures[0], asyncio.CancelledError)
    assert isinstance(failures[0].__cause__, OSError)
    assert str(failures[0].__cause__) == "synthetic cancelled close failure"


async def test_database_worker_preserves_runtime_and_operation_context(cancellation_database: AsyncEngine):
    journal = OperationJournal(async_sessionmaker(cancellation_database, expire_on_commit=False))
    owner = current_runtime()
    operation = OperationExecution(journal, "context")
    observed = []

    def clock():
        observed.append((current_runtime(), current_execution()))
        return datetime.now(UTC)

    journal.clock = clock
    with bind_execution(operation):
        await journal.accept(OperationSpec("world_restore", (ResourceReference("world", "survival", 1),), operation_id="context"))
        await journal.start("context")

    assert observed and all(value == (owner, operation) for value in observed)


async def test_failed_sql_write_rolls_back_before_next_writer(cancellation_database: AsyncEngine):
    journal = OperationJournal(async_sessionmaker(cancellation_database, expire_on_commit=False))
    await journal.accept(OperationSpec("world_restore", (ResourceReference("world", "survival", 1),), operation_id="failed"))

    def fail_after_update(_connection, _cursor, statement, _parameters, _context, _many):
        if statement.startswith("UPDATE operation_journal"):
            raise OSError("synthetic failure after sqlite update")

    event.listen(cancellation_database.sync_engine, "after_cursor_execute", fail_after_update)
    try:
        with pytest.raises(OSError, match="synthetic failure after sqlite update"):
            await journal.start("failed")
    finally:
        event.remove(cancellation_database.sync_engine, "after_cursor_execute", fail_after_update)

    assert not journal._lock.locked()
    record = await journal.get("failed")
    assert record is not None and record.state == OperationState.QUEUED
    independent = create_async_engine(cancellation_database.url, connect_args={"timeout": 0.1})
    try:
        other = OperationJournal(async_sessionmaker(independent, expire_on_commit=False))
        assert (await other.start("failed")).state == OperationState.RUNNING
    finally:
        await independent.dispose()
