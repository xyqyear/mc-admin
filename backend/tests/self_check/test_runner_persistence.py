import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models import Base, SelfCheckFinding, SelfCheckRun
from app.self_check.types import SelfCheckFindingResult


@pytest.fixture
async def self_check_db(monkeypatch: pytest.MonkeyPatch):
    temp_db = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    temp_db.close()

    engine = create_async_engine(f"sqlite+aiosqlite:///{temp_db.name}", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
    )

    import app.self_check.runner as runner_module

    monkeypatch.setattr(runner_module, "get_async_session", session_factory)
    yield session_factory

    await engine.dispose()
    Path(temp_db.name).unlink(missing_ok=True)


def _finding(check_id: str, severity: str, status: str) -> SelfCheckFindingResult:
    return SelfCheckFindingResult(
        check_id=check_id,
        category="test",
        severity=severity,  # type: ignore[arg-type]
        status=status,  # type: ignore[arg-type]
        title="Test check",
        message="Test result",
        evidence={},
        remediation=[],
        created_at=datetime.now(timezone.utc),
    )


def _install_checks(monkeypatch: pytest.MonkeyPatch, checks: dict):
    import app.self_check.runner as runner_module

    class TestSelfCheckConfig:
        retention_runs_keep_days = 14

        def enabled_check_ids(self) -> set[str]:
            return set(checks)

    monkeypatch.setattr(runner_module, "CHECK_IDS", tuple(checks))
    monkeypatch.setattr(
        runner_module,
        "CHECK_DEFINITIONS",
        {
            check_id: runner_module.CheckDefinition(
                check_id,
                "test",
                f"{check_id} title",
                f"{check_id} description",
                function,
            )
            for check_id, function in checks.items()
        },
    )
    monkeypatch.setattr(
        runner_module,
        "config",
        SimpleNamespace(self_check=TestSelfCheckConfig()),
    )
    return runner_module


async def test_successful_self_check_is_persisted(
    self_check_db, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def pass_check(context):
        return [_finding("test.pass", "success", "passed")]

    runner_module = _install_checks(monkeypatch, {"test.pass": pass_check})

    result = await runner_module.run_self_check(trigger="manual", requested_by_user_id=1)

    assert result.status == "success"
    assert result.scope == "full"

    async with self_check_db() as session:
        rows = (await session.execute(select(SelfCheckRun))).scalars().all()
        finding_count = (
            await session.execute(select(func.count(SelfCheckFinding.id)))
        ).scalar_one()
        assert len(rows) == 1
        assert rows[0].scope == "full"
        assert rows[0].check_id is None
        assert finding_count == 1


async def test_problem_self_check_is_persisted(
    self_check_db, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def warning_check(context):
        return [_finding("test.warning", "warning", "warning")]

    runner_module = _install_checks(monkeypatch, {"test.warning": warning_check})

    result = await runner_module.run_self_check(trigger="manual", requested_by_user_id=7)

    assert result.status == "warning"

    async with self_check_db() as session:
        run_count = (
            await session.execute(select(func.count(SelfCheckRun.id)))
        ).scalar_one()
        finding_count = (
            await session.execute(select(func.count(SelfCheckFinding.id)))
        ).scalar_one()
        assert run_count == 1
        assert finding_count == 1


async def test_run_persists_all_findings(
    self_check_db, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def mixed_check(context):
        return [
            _finding("test.pass", "success", "passed"),
            _finding("test.skip", "info", "skipped"),
            _finding("test.info", "info", "info"),
            _finding("test.warning", "warning", "warning"),
        ]

    runner_module = _install_checks(monkeypatch, {"test.mixed": mixed_check})

    result = await runner_module.run_self_check(trigger="manual", requested_by_user_id=7)

    assert result.status == "warning"
    assert result.summary.passed == 1
    assert result.summary.skipped == 1
    assert result.summary.info == 1
    assert result.summary.warning == 1

    async with self_check_db() as session:
        rows = (
            await session.execute(select(SelfCheckFinding).order_by(SelfCheckFinding.id))
        ).scalars().all()
        assert [row.check_id for row in rows] == [
            "test.pass",
            "test.skip",
            "test.info",
            "test.warning",
        ]


async def test_single_check_run_is_scoped(
    self_check_db, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def pass_check(context):
        return [_finding("test.pass", "success", "passed")]

    async def warning_check(context):
        return [_finding("test.warning", "warning", "warning")]

    runner_module = _install_checks(
        monkeypatch,
        {"test.pass": pass_check, "test.warning": warning_check},
    )

    result = await runner_module.run_self_check(
        trigger="manual",
        requested_by_user_id=7,
        check_ids=("test.warning",),
        scope="check",
    )

    assert result.status == "warning"
    assert result.scope == "check"
    assert result.check_id == "test.warning"
    assert [finding.check_id for finding in result.findings] == ["test.warning"]

    async with self_check_db() as session:
        run = (await session.execute(select(SelfCheckRun))).scalar_one()
        assert run.scope == "check"
        assert run.check_id == "test.warning"


async def test_run_stream_emits_check_events(
    self_check_db, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def pass_check(context):
        return [_finding("test.pass", "success", "passed")]

    runner_module = _install_checks(monkeypatch, {"test.pass": pass_check})

    events = [
        event
        async for event in runner_module.iter_self_check_events(
            trigger="manual",
            requested_by_user_id=1,
        )
    ]

    assert [event.type for event in events] == [
        "started",
        "check_started",
        "check_finished",
        "completed",
    ]
    assert events[-1].result is not None
    assert events[-1].result.status == "success"


async def test_retention_prunes_all_old_runs(
    self_check_db, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def pass_check(context):
        return [_finding("test.pass", "success", "passed")]

    runner_module = _install_checks(monkeypatch, {"test.pass": pass_check})

    async with self_check_db() as session:
        old_started = datetime.now(timezone.utc) - timedelta(days=15, minutes=1)
        old_finished = old_started + timedelta(seconds=1)
        session.add(
            SelfCheckRun(
                id="old",
                trigger="manual",
                scope="full",
                check_id=None,
                status="success",
                started_at=old_started,
                finished_at=old_finished,
                summary_json='{"total":1,"passed":1,"skipped":0,"info":0,"warning":0,"critical":0,"failed":0,"status":"success"}',
                requested_by_user_id=None,
                error_message=None,
            )
        )
        session.add(
            SelfCheckFinding(
                run_id="old",
                check_id="test.pass",
                category="test",
                severity="success",
                status="passed",
                server_id=None,
                title="Old",
                message="Old",
                evidence_json="{}",
                remediation_json="[]",
                created_at=old_finished,
            )
        )
        await session.commit()

    result = await runner_module.run_self_check(trigger="manual", requested_by_user_id=1)

    async with self_check_db() as session:
        run_ids = [
            row_id
            for row_id in (
                await session.execute(
                    select(SelfCheckRun.id).order_by(SelfCheckRun.id.asc())
                )
            ).scalars()
        ]
        finding_count = (
            await session.execute(select(func.count(SelfCheckFinding.id)))
        ).scalar_one()
        assert run_ids == [result.id]
        assert finding_count == 1
