from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models import Base, SelfCheckFinding, SelfCheckRun
from app.self_check import crud


@pytest.fixture
async def self_check_db(tmp_path: Path):
    db_path = tmp_path / "self_check_current_state.sqlite3"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
    )
    yield session_factory

    await engine.dispose()


BASE_TIME = datetime(2026, 6, 6, 12, 0, tzinfo=timezone.utc)


def at(minutes: int) -> datetime:
    return BASE_TIME + timedelta(minutes=minutes)


def add_run(
    session: AsyncSession,
    *,
    run_id: str,
    scope: str,
    finished_minute: int,
    check_id: str | None = None,
    status: str = "success",
) -> None:
    finished_at = at(finished_minute)
    session.add(
        SelfCheckRun(
            id=run_id,
            trigger="manual",
            scope=scope,
            check_id=check_id,
            status=status,
            started_at=finished_at - timedelta(seconds=2),
            finished_at=finished_at,
            summary_json='{"total":1,"passed":1,"skipped":0,"info":0,"warning":0,"critical":0,"failed":0,"status":"success"}',
            requested_by_user_id=None,
            error_message=None,
        )
    )


def add_finding(
    session: AsyncSession,
    *,
    run_id: str,
    check_id: str,
    severity: str,
    status: str,
    server_id: str | None = None,
    title: str | None = None,
) -> None:
    session.add(
        SelfCheckFinding(
            run_id=run_id,
            check_id=check_id,
            category="test",
            severity=severity,
            status=status,
            server_id=server_id,
            title=title or check_id,
            message=f"{check_id} {status}",
            evidence_json=f'{{"run_id":"{run_id}"}}',
            remediation_json="[]",
            created_at=BASE_TIME,
        )
    )


def finding_keys(state) -> list[tuple[str, str | None, str, str, str]]:
    return [
        (
            finding.check_id,
            finding.server_id,
            finding.severity,
            finding.status,
            finding.evidence["run_id"],
        )
        for finding in state.findings
    ]


async def test_current_state_is_none_without_full_run(self_check_db) -> None:
    async with self_check_db() as session:
        add_run(
            session,
            run_id="check-a",
            scope="check",
            check_id="check.a",
            finished_minute=10,
        )
        add_finding(
            session,
            run_id="check-a",
            check_id="check.a",
            severity="success",
            status="passed",
        )
        await session.commit()

        assert await crud.get_current_state(session) is None


async def test_current_state_uses_latest_full_run_when_no_patches(
    self_check_db,
) -> None:
    async with self_check_db() as session:
        add_run(session, run_id="full-old", scope="full", finished_minute=5)
        add_finding(
            session,
            run_id="full-old",
            check_id="check.a",
            severity="critical",
            status="critical",
        )
        add_run(session, run_id="full-new", scope="full", finished_minute=10)
        add_finding(
            session,
            run_id="full-new",
            check_id="check.a",
            severity="success",
            status="passed",
        )
        add_finding(
            session,
            run_id="full-new",
            check_id="check.b",
            severity="warning",
            status="warning",
            server_id="s1",
        )
        await session.commit()

        state = await crud.get_current_state(session)

    assert state is not None
    assert state.source_run_id == "full-new"
    assert state.updated_at == at(10)
    assert state.status == "warning"
    assert state.summary.total == 2
    assert state.summary.passed == 1
    assert state.summary.warning == 1
    assert finding_keys(state) == [
        ("check.a", None, "success", "passed", "full-new"),
        ("check.b", "s1", "warning", "warning", "full-new"),
    ]


async def test_single_check_patch_replaces_all_baseline_findings_for_check_id(
    self_check_db,
) -> None:
    async with self_check_db() as session:
        add_run(session, run_id="full", scope="full", finished_minute=10)
        add_finding(
            session,
            run_id="full",
            check_id="check.a",
            severity="success",
            status="passed",
        )
        add_finding(
            session,
            run_id="full",
            check_id="check.b",
            severity="warning",
            status="warning",
            server_id="s1",
        )
        add_finding(
            session,
            run_id="full",
            check_id="check.b",
            severity="warning",
            status="warning",
            server_id="s2",
        )
        add_run(
            session,
            run_id="patch-b",
            scope="check",
            check_id="check.b",
            finished_minute=15,
        )
        add_finding(
            session,
            run_id="patch-b",
            check_id="check.b",
            severity="success",
            status="passed",
        )
        await session.commit()

        state = await crud.get_current_state(session)

    assert state is not None
    assert state.source_run_id == "patch-b"
    assert state.updated_at == at(15)
    assert state.status == "success"
    assert state.summary.total == 2
    assert finding_keys(state) == [
        ("check.a", None, "success", "passed", "full"),
        ("check.b", None, "success", "passed", "patch-b"),
    ]


async def test_latest_patch_per_check_id_wins(self_check_db) -> None:
    async with self_check_db() as session:
        add_run(session, run_id="full", scope="full", finished_minute=10)
        add_finding(
            session,
            run_id="full",
            check_id="check.a",
            severity="success",
            status="passed",
        )
        add_finding(
            session,
            run_id="full",
            check_id="check.c",
            severity="success",
            status="passed",
        )
        add_run(
            session,
            run_id="patch-c-old",
            scope="check",
            check_id="check.c",
            finished_minute=12,
        )
        add_finding(
            session,
            run_id="patch-c-old",
            check_id="check.c",
            severity="warning",
            status="warning",
            server_id="old",
        )
        add_run(
            session,
            run_id="patch-c-new",
            scope="check",
            check_id="check.c",
            finished_minute=20,
        )
        add_finding(
            session,
            run_id="patch-c-new",
            check_id="check.c",
            severity="critical",
            status="failed",
            server_id="new",
        )
        await session.commit()

        state = await crud.get_current_state(session)

    assert state is not None
    assert state.source_run_id == "patch-c-new"
    assert state.status == "critical"
    assert state.summary.failed == 1
    assert finding_keys(state) == [
        ("check.a", None, "success", "passed", "full"),
        ("check.c", "new", "critical", "failed", "patch-c-new"),
    ]


async def test_patch_before_latest_full_run_is_ignored(self_check_db) -> None:
    async with self_check_db() as session:
        add_run(
            session,
            run_id="patch-before",
            scope="check",
            check_id="check.a",
            finished_minute=5,
        )
        add_finding(
            session,
            run_id="patch-before",
            check_id="check.a",
            severity="critical",
            status="critical",
        )
        add_run(session, run_id="full", scope="full", finished_minute=10)
        add_finding(
            session,
            run_id="full",
            check_id="check.a",
            severity="success",
            status="passed",
        )
        await session.commit()

        state = await crud.get_current_state(session)

    assert state is not None
    assert state.source_run_id == "full"
    assert state.status == "success"
    assert finding_keys(state) == [
        ("check.a", None, "success", "passed", "full"),
    ]


async def test_new_full_run_resets_older_patches(self_check_db) -> None:
    async with self_check_db() as session:
        add_run(session, run_id="full-old", scope="full", finished_minute=10)
        add_finding(
            session,
            run_id="full-old",
            check_id="check.b",
            severity="warning",
            status="warning",
        )
        add_run(
            session,
            run_id="patch-b",
            scope="check",
            check_id="check.b",
            finished_minute=12,
        )
        add_finding(
            session,
            run_id="patch-b",
            check_id="check.b",
            severity="success",
            status="passed",
        )
        add_run(session, run_id="full-new", scope="full", finished_minute=20)
        add_finding(
            session,
            run_id="full-new",
            check_id="check.b",
            severity="warning",
            status="warning",
            server_id="new",
        )
        await session.commit()

        state = await crud.get_current_state(session)

    assert state is not None
    assert state.source_run_id == "full-new"
    assert state.status == "warning"
    assert finding_keys(state) == [
        ("check.b", "new", "warning", "warning", "full-new"),
    ]


async def test_patch_run_can_have_multiple_current_findings(
    self_check_db,
) -> None:
    async with self_check_db() as session:
        add_run(session, run_id="full", scope="full", finished_minute=10)
        add_finding(
            session,
            run_id="full",
            check_id="check.b",
            severity="success",
            status="passed",
        )
        add_run(
            session,
            run_id="patch-b",
            scope="check",
            check_id="check.b",
            finished_minute=15,
        )
        add_finding(
            session,
            run_id="patch-b",
            check_id="check.b",
            severity="warning",
            status="warning",
            server_id="s1",
        )
        add_finding(
            session,
            run_id="patch-b",
            check_id="check.b",
            severity="warning",
            status="warning",
            server_id="s2",
        )
        await session.commit()

        state = await crud.get_current_state(session)

    assert state is not None
    assert state.source_run_id == "patch-b"
    assert state.status == "warning"
    assert state.summary.total == 2
    assert state.summary.warning == 2
    assert finding_keys(state) == [
        ("check.b", "s1", "warning", "warning", "patch-b"),
        ("check.b", "s2", "warning", "warning", "patch-b"),
    ]


async def test_empty_full_run_still_produces_empty_success_state(
    self_check_db,
) -> None:
    async with self_check_db() as session:
        add_run(session, run_id="empty-full", scope="full", finished_minute=10)
        await session.commit()

        state = await crud.get_current_state(session)

    assert state is not None
    assert state.source_run_id == "empty-full"
    assert state.updated_at == at(10)
    assert state.status == "success"
    assert state.summary.total == 0
    assert state.findings == []


async def test_current_state_excludes_disabled_baseline_findings(
    self_check_db,
) -> None:
    async with self_check_db() as session:
        add_run(session, run_id="full", scope="full", finished_minute=10)
        add_finding(
            session,
            run_id="full",
            check_id="check.a",
            severity="warning",
            status="warning",
        )
        add_finding(
            session,
            run_id="full",
            check_id="check.b",
            severity="success",
            status="passed",
        )
        await session.commit()

        state = await crud.get_current_state(
            session,
            enabled_check_ids={"check.b"},
        )

    assert state is not None
    assert state.source_run_id == "full"
    assert state.status == "success"
    assert state.summary.total == 1
    assert finding_keys(state) == [
        ("check.b", None, "success", "passed", "full"),
    ]


async def test_current_state_excludes_disabled_patch_findings(
    self_check_db,
) -> None:
    async with self_check_db() as session:
        add_run(session, run_id="full", scope="full", finished_minute=10)
        add_finding(
            session,
            run_id="full",
            check_id="check.a",
            severity="success",
            status="passed",
        )
        add_finding(
            session,
            run_id="full",
            check_id="check.b",
            severity="success",
            status="passed",
        )
        add_run(
            session,
            run_id="patch-b",
            scope="check",
            check_id="check.b",
            finished_minute=15,
        )
        add_finding(
            session,
            run_id="patch-b",
            check_id="check.b",
            severity="warning",
            status="warning",
        )
        await session.commit()

        state = await crud.get_current_state(
            session,
            enabled_check_ids={"check.a"},
        )

    assert state is not None
    assert state.source_run_id == "full"
    assert state.status == "success"
    assert state.summary.total == 1
    assert finding_keys(state) == [
        ("check.a", None, "success", "passed", "full"),
    ]


async def test_current_state_can_project_to_no_enabled_findings(
    self_check_db,
) -> None:
    async with self_check_db() as session:
        add_run(session, run_id="full", scope="full", finished_minute=10)
        add_finding(
            session,
            run_id="full",
            check_id="check.a",
            severity="warning",
            status="warning",
        )
        await session.commit()

        state = await crud.get_current_state(session, enabled_check_ids=set())

    assert state is not None
    assert state.source_run_id == "full"
    assert state.updated_at == at(10)
    assert state.status == "success"
    assert state.summary.total == 0
    assert state.findings == []


async def test_tie_breaker_uses_run_id_when_finished_at_matches(
    self_check_db,
) -> None:
    async with self_check_db() as session:
        add_run(session, run_id="full", scope="full", finished_minute=10)
        add_finding(
            session,
            run_id="full",
            check_id="check.a",
            severity="success",
            status="passed",
        )
        add_run(
            session,
            run_id="patch-a-1",
            scope="check",
            check_id="check.a",
            finished_minute=15,
        )
        add_finding(
            session,
            run_id="patch-a-1",
            check_id="check.a",
            severity="warning",
            status="warning",
        )
        add_run(
            session,
            run_id="patch-a-2",
            scope="check",
            check_id="check.a",
            finished_minute=15,
        )
        add_finding(
            session,
            run_id="patch-a-2",
            check_id="check.a",
            severity="success",
            status="passed",
        )
        await session.commit()

        state = await crud.get_current_state(session)

    assert state is not None
    assert state.source_run_id == "patch-a-2"
    assert finding_keys(state) == [
        ("check.a", None, "success", "passed", "patch-a-2"),
    ]
