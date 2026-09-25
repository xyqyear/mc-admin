import asyncio
from typing import Literal

import anyio
import pytest
from sqlalchemy import event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Session
from sqlalchemy.util import await_only

from app.background_tasks.manager import BackgroundTaskManager
from app.background_tasks.types import TaskProgress, TaskType
from app.operations.execution import operation_scope
from app.operations.journal import OperationJournal
from app.operations.journal_types import (
    OperationSpec,
    OperationState,
    ResourceReference,
)


@pytest.fixture
def acceptance_runtime(journal, isolated_runtime):
    previous = isolated_runtime.journal
    isolated_runtime.journal = journal
    try:
        yield isolated_runtime
    finally:
        isolated_runtime.journal = previous


@pytest.mark.parametrize(("origin", "close_failure"), [("request", False), ("task", False), ("task", True)])
@pytest.mark.parametrize("cancellation", ["anyio", "asyncio"])
async def test_cancelled_acceptance_settles_committed_record_without_executing(
    journal, acceptance_runtime, origin, close_failure, cancellation,
):
    manager = BackgroundTaskManager(journal)
    committed, release = asyncio.Event(), asyncio.Event()
    reached_external_work = False
    failures: list[BaseException] = []
    engine = journal.session_factory.kw["bind"]

    def pause_after_commit(session):
        if session.bind is engine.sync_engine and not committed.is_set():
            committed.set()
            await_only(release.wait())

    async def operation():
        nonlocal reached_external_work
        try:
            if close_failure:
                yield TaskProgress(message="prepared cleanup")
            reached_external_work = True
            yield TaskProgress(progress=100)
        finally:
            if close_failure:
                raise OSError("synthetic unsubmitted generator cleanup failure")

    generator = operation()
    if close_failure:
        await anext(generator)

    async def invoke():
        nonlocal reached_external_work
        try:
            if origin == "request":
                async with operation_scope("snapshot_backup", [], origin="request"):
                    reached_external_work = True
            else:
                await manager.submit_durable(TaskType.ARCHIVE_CREATE, "cancelled admission", generator)
                reached_external_work = True
        except BaseException as error:
            failures.append(error)
            raise

    event.listen(Session, "after_commit", pause_after_commit)
    try:
        if cancellation == "anyio":
            async with anyio.create_task_group() as group:
                group.start_soon(invoke)
                try:
                    with anyio.fail_after(3):
                        await committed.wait()
                    group.cancel_scope.cancel()
                finally:
                    release.set()
        else:
            owner = asyncio.create_task(invoke())
            try:
                await asyncio.wait_for(committed.wait(), 3)
                owner.cancel("cancel during accepted commit")
                release.set()
                with pytest.raises(asyncio.CancelledError):
                    await owner
            finally:
                release.set()
                if not owner.done():
                    owner.cancel()
                await asyncio.gather(owner, return_exceptions=True)

        assert len(failures) == 1 and isinstance(failures[0], asyncio.CancelledError)
        if close_failure:
            assert isinstance(failures[0].__cause__, OSError)
        assert not reached_external_work
        records = await journal.list()
        assert len(records) == 1
        record = records[0]
        assert record.state is (OperationState.INTERRUPTED if origin == "request" else OperationState.CANCELLED)
        assert record.writers_stopped and record.ended_at is not None
        assert not record.processes
        assert await journal.unsettled() == []
        if origin == "task":
            with pytest.raises(StopAsyncIteration):
                await anext(generator)
            assert manager.get_task(record.operation_id) is None
    finally:
        event.remove(Session, "after_commit", pause_after_commit)
        release.set()
        await generator.aclose()
        await manager.shutdown()


async def test_duplicate_task_admission_preserves_existing_record_and_closes_generator(journal):
    manager = BackgroundTaskManager(journal)
    original = await journal.accept(OperationSpec(
        "archive_create", (ResourceReference("archive"),), origin="task", operation_id="same-task",
    ))

    async def operation():
        pytest.fail("Rejected duplicate task executed")
        yield TaskProgress(progress=100)

    generator = operation()
    try:
        with pytest.raises(IntegrityError):
            await manager.submit_durable(TaskType.ARCHIVE_CREATE, "duplicate", generator, task_id=original.operation_id)
        assert await journal.get(original.operation_id) == original
        with pytest.raises(StopAsyncIteration):
            await anext(generator)
    finally:
        await generator.aclose()
        await manager.shutdown()


@pytest.mark.parametrize("origin", ["request", "task"])
async def test_already_cancelled_admission_does_not_create_record(journal, acceptance_runtime, origin):
    manager = BackgroundTaskManager(journal)

    async def operation():
        pytest.fail("Cancelled task executed")
        yield TaskProgress(progress=100)

    generator = operation()
    try:
        with anyio.CancelScope() as scope:
            scope.cancel()
            if origin == "request":
                async with operation_scope("snapshot_backup", [], origin="request"):
                    pytest.fail("Cancelled request executed")
            else:
                await manager.submit_durable(TaskType.ARCHIVE_CREATE, "cancelled", generator)
                pytest.fail("Cancelled task accepted")
        assert scope.cancelled_caught
        assert await journal.list() == []
        if origin == "task":
            with pytest.raises(StopAsyncIteration):
                await anext(generator)
    finally:
        await generator.aclose()
        await manager.shutdown()


@pytest.mark.parametrize("origin", ["request", "task"])
@pytest.mark.parametrize("cancellation", ["anyio", "asyncio"])
async def test_waiting_admission_cancels_without_acquiring_database_writer(
    journal, acceptance_runtime, origin, cancellation,
):
    manager = BackgroundTaskManager(journal)
    waiting = asyncio.Event()
    finished = asyncio.Event()

    class ObservedLock(asyncio.Lock):
        async def acquire(self) -> Literal[True]:
            if self.locked():
                waiting.set()
            return await super().acquire()

    journal._lock = ObservedLock()

    async def operation():
        pytest.fail("Cancelled waiting task executed")
        yield TaskProgress(progress=100)

    generator = operation()

    async def invoke():
        try:
            if origin == "request":
                async with operation_scope("snapshot_backup", [], origin="request"):
                    pytest.fail("Cancelled waiting request executed")
            else:
                await manager.submit_durable(TaskType.ARCHIVE_CREATE, "cancelled waiting", generator)
                pytest.fail("Cancelled waiting task accepted")
        finally:
            finished.set()

    await journal._lock.acquire()
    try:
        if cancellation == "anyio":
            async with anyio.create_task_group() as group:
                group.start_soon(invoke)
                await waiting.wait()
                group.cancel_scope.cancel()
                with anyio.CancelScope(shield=True):
                    try:
                        with anyio.fail_after(2):
                            await finished.wait()
                    except TimeoutError:
                        journal._lock.release()
                        await finished.wait()
                        raise
        else:
            owner = asyncio.create_task(invoke())
            try:
                await waiting.wait()
                owner.cancel("cancel waiting admission")
                with pytest.raises(asyncio.CancelledError):
                    await asyncio.wait_for(asyncio.shield(owner), 2)
            finally:
                if not owner.done():
                    journal._lock.release()
                    owner.cancel()
                await asyncio.gather(owner, return_exceptions=True)
        assert journal._lock.locked()
        assert await journal.list() == []
        if origin == "task":
            with pytest.raises(StopAsyncIteration):
                await anext(generator)
    finally:
        if journal._lock.locked():
            journal._lock.release()
        await generator.aclose()
        await manager.shutdown()


@pytest.mark.parametrize("origin", ["request", "task"])
@pytest.mark.parametrize("cancellation", [None, "anyio", "asyncio"])
async def test_committed_acceptance_is_settled_when_session_close_fails(
    journal, acceptance_runtime, origin, cancellation,
):
    original_factory = journal.session_factory
    closing, release = asyncio.Event(), asyncio.Event()
    failures: list[BaseException] = []
    if cancellation is None:
        release.set()

    class CloseFailure(AsyncSession):
        async def close(self) -> None:
            closing.set()
            await release.wait()
            await super().close()
            raise OSError("synthetic postcommit close failure")

    journal.session_factory = async_sessionmaker[AsyncSession](
        original_factory.kw["bind"], class_=CloseFailure, expire_on_commit=False,
    )
    manager = BackgroundTaskManager(journal)

    async def operation():
        pytest.fail("Admission with failed session cleanup executed")
        yield TaskProgress(progress=100)

    generator = operation()

    async def invoke():
        try:
            if origin == "request":
                async with operation_scope("snapshot_backup", [], origin="request"):
                    pytest.fail("Admission with failed session cleanup executed")
            else:
                await manager.submit_durable(TaskType.ARCHIVE_CREATE, "failed close", generator)
                pytest.fail("Admission with failed session cleanup executed")
        except BaseException as error:
            failures.append(error)
            raise

    try:
        if cancellation == "anyio":
            async with anyio.create_task_group() as group:
                group.start_soon(invoke)
                try:
                    with anyio.fail_after(3):
                        await closing.wait()
                    group.cancel_scope.cancel()
                finally:
                    release.set()
        elif cancellation == "asyncio":
            owner = asyncio.create_task(invoke())
            try:
                await asyncio.wait_for(closing.wait(), 3)
                owner.cancel("cancel during postcommit close")
                release.set()
                with pytest.raises(asyncio.CancelledError):
                    await owner
            finally:
                release.set()
                await asyncio.gather(owner, return_exceptions=True)
        else:
            with pytest.raises(OSError, match="synthetic postcommit close failure"):
                await invoke()

        assert len(failures) == 1
        assert isinstance(failures[0], asyncio.CancelledError if cancellation else OSError)
        independent = OperationJournal(original_factory)
        records = await independent.list()
        assert len(records) == 1
        expected = OperationState.FAILED if cancellation is None else (
            OperationState.INTERRUPTED if origin == "request" else OperationState.CANCELLED
        )
        assert records[0].state is expected
        assert records[0].writers_stopped and records[0].ended_at is not None
        assert await independent.unsettled() == []
        if origin == "task":
            with pytest.raises(StopAsyncIteration):
                await anext(generator)
            assert manager.get_task(records[0].operation_id) is None
    finally:
        release.set()
        journal.session_factory = original_factory
        await generator.aclose()
        await manager.shutdown()
