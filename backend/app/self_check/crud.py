"""Persistence helpers for retained self-check runs."""

import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, literal, select, true, union_all
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import SelfCheckFinding, SelfCheckRun
from .types import (
    SelfCheckCurrentState,
    SelfCheckFindingResult,
    SelfCheckRunDetail,
    SelfCheckRunResult,
    SelfCheckRunSummaryRecord,
    SelfCheckSummary,
)


def _summary_from_row(row: SelfCheckRun) -> SelfCheckSummary:
    return SelfCheckSummary.model_validate(json.loads(row.summary_json))


def _duration_ms(row: SelfCheckRun) -> int:
    return int((row.finished_at - row.started_at).total_seconds() * 1000)


def _finding_from_row(row: SelfCheckFinding) -> SelfCheckFindingResult:
    return SelfCheckFindingResult(
        check_id=row.check_id,
        category=row.category,
        severity=row.severity,  # type: ignore[arg-type]
        status=row.status,  # type: ignore[arg-type]
        server_id=row.server_id,
        title=row.title,
        message=row.message,
        evidence=json.loads(row.evidence_json or "{}"),
        remediation=json.loads(row.remediation_json or "[]"),
        created_at=row.created_at,
    )


def _finding_from_mapping(row) -> SelfCheckFindingResult:
    return SelfCheckFindingResult(
        check_id=row.check_id,
        category=row.category,
        severity=row.severity,
        status=row.status,
        server_id=row.server_id,
        title=row.title,
        message=row.message,
        evidence=json.loads(row.evidence_json or "{}"),
        remediation=json.loads(row.remediation_json or "[]"),
        created_at=row.created_at,
    )


def _run_summary_from_row(row: SelfCheckRun) -> SelfCheckRunSummaryRecord:
    return SelfCheckRunSummaryRecord(
        id=row.id,
        trigger=row.trigger,
        scope=row.scope,  # type: ignore[arg-type]
        check_id=row.check_id,
        status=row.status,  # type: ignore[arg-type]
        started_at=row.started_at,
        finished_at=row.finished_at,
        duration_ms=_duration_ms(row),
        summary=_summary_from_row(row),
        requested_by_user_id=row.requested_by_user_id,
        error_message=row.error_message,
    )


def summarize_findings(findings: list[SelfCheckFindingResult]) -> SelfCheckSummary:
    warning = sum(1 for finding in findings if finding.severity == "warning")
    critical = sum(1 for finding in findings if finding.severity == "critical")
    failed = sum(1 for finding in findings if finding.status == "failed")
    status = "critical" if critical or failed else "warning" if warning else "success"
    return SelfCheckSummary(
        total=len(findings),
        passed=sum(1 for finding in findings if finding.status == "passed"),
        skipped=sum(1 for finding in findings if finding.status == "skipped"),
        info=sum(
            1
            for finding in findings
            if finding.severity == "info" and finding.status != "skipped"
        ),
        warning=warning,
        critical=critical,
        failed=failed,
        status=status,  # type: ignore[arg-type]
    )


async def persist_run(
    session: AsyncSession,
    result: SelfCheckRunResult,
    *,
    requested_by_user_id: int | None = None,
) -> None:
    row = SelfCheckRun(
        id=result.id,
        trigger=result.trigger,
        scope=result.scope,
        check_id=result.check_id,
        status=result.status,
        started_at=result.started_at,
        finished_at=result.finished_at,
        summary_json=result.summary.model_dump_json(),
        requested_by_user_id=requested_by_user_id,
        error_message=result.error_message,
    )
    session.add(row)

    for finding in result.findings:
        session.add(
            SelfCheckFinding(
                run_id=result.id,
                check_id=finding.check_id,
                category=finding.category,
                severity=finding.severity,
                status=finding.status,
                server_id=finding.server_id,
                title=finding.title,
                message=finding.message,
                evidence_json=json.dumps(finding.evidence, ensure_ascii=False),
                remediation_json=json.dumps(
                    finding.remediation, ensure_ascii=False
                ),
                created_at=finding.created_at,
            )
        )

    await session.commit()


async def count_runs(session: AsyncSession) -> int:
    result = await session.execute(select(func.count(SelfCheckRun.id)))
    return int(result.scalar_one())


async def list_runs(
    session: AsyncSession, *, limit: int, offset: int
) -> list[SelfCheckRunSummaryRecord]:
    result = await session.execute(
        select(SelfCheckRun)
        .order_by(SelfCheckRun.finished_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return [_run_summary_from_row(row) for row in result.scalars().all()]


def _current_findings_statement(enabled_check_ids: set[str] | None = None):
    run = SelfCheckRun.__table__
    finding = SelfCheckFinding.__table__
    enabled_ids = (
        tuple(sorted(enabled_check_ids))
        if enabled_check_ids is not None
        else None
    )

    latest_full = (
        select(
            run.c.id.label("run_id"),
            run.c.finished_at.label("finished_at"),
        )
        .where(run.c.scope == "full")
        .order_by(run.c.finished_at.desc(), run.c.id.desc())
        .limit(1)
        .cte("latest_full")
    )

    ranked_patch_filters = [
        run.c.scope == "check",
        run.c.check_id.is_not(None),
        run.c.finished_at > latest_full.c.finished_at,
    ]
    if enabled_ids is not None:
        ranked_patch_filters.append(run.c.check_id.in_(enabled_ids))

    ranked_patch_runs = (
        select(
            run.c.id.label("run_id"),
            run.c.check_id.label("check_id"),
            run.c.finished_at.label("finished_at"),
            func.row_number()
            .over(
                partition_by=run.c.check_id,
                order_by=(run.c.finished_at.desc(), run.c.id.desc()),
            )
            .label("rn"),
        )
        .select_from(run.join(latest_full, true()))
        .where(*ranked_patch_filters)
        .cte("ranked_patch_runs")
    )

    latest_patch_runs = (
        select(
            ranked_patch_runs.c.run_id,
            ranked_patch_runs.c.check_id,
            ranked_patch_runs.c.finished_at,
        )
        .where(ranked_patch_runs.c.rn == 1)
        .cte("latest_patch_runs")
    )

    patch_exists = (
        select(literal(1))
        .select_from(latest_patch_runs)
        .where(latest_patch_runs.c.check_id == finding.c.check_id)
        .exists()
    )

    baseline_filters = [~patch_exists]
    if enabled_ids is not None:
        baseline_filters.append(finding.c.check_id.in_(enabled_ids))

    baseline_findings = (
        select(
            finding.c.id,
            finding.c.run_id,
            finding.c.check_id,
            finding.c.category,
            finding.c.severity,
            finding.c.status,
            finding.c.server_id,
            finding.c.title,
            finding.c.message,
            finding.c.evidence_json,
            finding.c.remediation_json,
            finding.c.created_at,
            latest_full.c.run_id.label("source_run_id"),
            latest_full.c.finished_at.label("source_finished_at"),
        )
        .select_from(
            finding.join(latest_full, finding.c.run_id == latest_full.c.run_id)
        )
        .where(*baseline_filters)
    )

    patch_filters = []
    if enabled_ids is not None:
        patch_filters.append(finding.c.check_id.in_(enabled_ids))

    patch_findings = (
        select(
            finding.c.id,
            finding.c.run_id,
            finding.c.check_id,
            finding.c.category,
            finding.c.severity,
            finding.c.status,
            finding.c.server_id,
            finding.c.title,
            finding.c.message,
            finding.c.evidence_json,
            finding.c.remediation_json,
            finding.c.created_at,
            latest_patch_runs.c.run_id.label("source_run_id"),
            latest_patch_runs.c.finished_at.label("source_finished_at"),
        )
        .select_from(
            finding.join(
                latest_patch_runs,
                finding.c.run_id == latest_patch_runs.c.run_id,
            )
        )
        .where(*patch_filters)
    )

    current_findings = union_all(baseline_findings, patch_findings).cte(
        "current_findings"
    )
    state_sources = union_all(
        select(
            latest_full.c.run_id.label("source_run_id"),
            latest_full.c.finished_at.label("updated_at"),
        ),
        select(
            latest_patch_runs.c.run_id.label("source_run_id"),
            latest_patch_runs.c.finished_at.label("updated_at"),
        ),
    ).cte("state_sources")
    state_meta = (
        select(
            state_sources.c.source_run_id,
            state_sources.c.updated_at,
        )
        .order_by(state_sources.c.updated_at.desc(), state_sources.c.source_run_id.desc())
        .limit(1)
        .cte("state_meta")
    )

    return (
        select(
            current_findings.c.id,
            current_findings.c.run_id,
            current_findings.c.check_id,
            current_findings.c.category,
            current_findings.c.severity,
            current_findings.c.status,
            current_findings.c.server_id,
            current_findings.c.title,
            current_findings.c.message,
            current_findings.c.evidence_json,
            current_findings.c.remediation_json,
            current_findings.c.created_at,
            current_findings.c.source_run_id,
            current_findings.c.source_finished_at,
            state_meta.c.source_run_id.label("state_source_run_id"),
            state_meta.c.updated_at.label("state_updated_at"),
        )
        .select_from(state_meta.outerjoin(current_findings, true()))
        .order_by(
            current_findings.c.check_id,
            current_findings.c.server_id,
            current_findings.c.id,
        )
    )


async def get_current_state(
    session: AsyncSession,
    *,
    enabled_check_ids: set[str] | None = None,
) -> SelfCheckCurrentState | None:
    rows = (
        await session.execute(
            _current_findings_statement(enabled_check_ids=enabled_check_ids)
        )
    ).all()
    if not rows:
        return None

    first = rows[0]
    source_run_id = first.state_source_run_id
    updated_at = first.state_updated_at
    if source_run_id is None or updated_at is None:
        return None

    findings = [
        _finding_from_mapping(row)
        for row in rows
        if row.id is not None
    ]
    summary = summarize_findings(findings)
    return SelfCheckCurrentState(
        status=summary.status,
        updated_at=updated_at,
        source_run_id=source_run_id,
        summary=summary,
        findings=findings,
    )


async def get_run(session: AsyncSession, run_id: str) -> SelfCheckRunDetail | None:
    run = (
        await session.execute(select(SelfCheckRun).where(SelfCheckRun.id == run_id))
    ).scalar_one_or_none()
    if run is None:
        return None

    findings = (
        (
            await session.execute(
                select(SelfCheckFinding)
                .where(SelfCheckFinding.run_id == run_id)
                .order_by(SelfCheckFinding.id.asc())
            )
        )
        .scalars()
        .all()
    )
    return SelfCheckRunDetail(
        **_run_summary_from_row(run).model_dump(),
        findings=[_finding_from_row(row) for row in findings],
    )


async def prune_runs(session: AsyncSession, *, keep_days: int) -> int:
    if keep_days <= 0:
        return 0

    cutoff = datetime.now(timezone.utc) - timedelta(days=keep_days)
    old_run_ids = [
        row_id
        for row_id in (
            await session.execute(
                select(SelfCheckRun.id).where(SelfCheckRun.finished_at < cutoff)
            )
        ).scalars()
    ]
    if not old_run_ids:
        return 0

    await session.execute(
        delete(SelfCheckFinding).where(SelfCheckFinding.run_id.in_(old_run_ids))
    )
    await session.execute(delete(SelfCheckRun).where(SelfCheckRun.id.in_(old_run_ids)))
    await session.commit()
    return len(old_run_ids)
