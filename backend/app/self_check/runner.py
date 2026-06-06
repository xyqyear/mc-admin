"""Self-check runner orchestration."""

import asyncio
import secrets
from datetime import datetime, timezone
from typing import AsyncIterator

from ..db.database import get_async_session
from ..dynamic_config import config
from ..logger import logger
from . import crud
from .checks import (
    CHECK_DEFINITIONS,
    BackupJarMatch,
    CheckDefinition,
    PermissionScanResult,
    SelfCheckContext,
    _find_backup_jars_sync,
    _finding,
    _scan_permission_owner_with_fd,
    _skipped,
    _success,
)
from .constants import CHECK_IDS
from .notifications import self_check_notification_bus
from .types import (
    SelfCheckCatalogItem,
    SelfCheckFindingResult,
    SelfCheckRunEvent,
    SelfCheckRunResult,
    SelfCheckRunScope,
    SelfCheckSummary,
)


_run_lock = asyncio.Lock()


def get_catalog() -> list[SelfCheckCatalogItem]:
    enabled = config.self_check.enabled_check_ids()
    return [
        SelfCheckCatalogItem(
            check_id=definition.check_id,
            category=definition.category,
            title=definition.title,
            description=definition.description,
            enabled=definition.check_id in enabled,
        )
        for check_id in CHECK_IDS
        if (definition := CHECK_DEFINITIONS.get(check_id)) is not None
    ]


def _summarize(findings: list[SelfCheckFindingResult]) -> SelfCheckSummary:
    return crud.summarize_findings(findings)


def validate_check_id(check_id: str) -> CheckDefinition:
    try:
        return CHECK_DEFINITIONS[check_id]
    except KeyError as exc:
        raise ValueError(f"未知的自检项: {check_id}") from exc


async def _run_definition(
    definition: CheckDefinition,
    context: SelfCheckContext,
    enabled: set[str],
) -> list[SelfCheckFindingResult]:
    if definition.check_id not in enabled:
        return _skipped(definition, "该自检项已被禁用。")

    try:
        return await definition.function(context)
    except Exception as exc:
        logger.exception("self-check failed: %s", definition.check_id)
        return [
            _finding(
                check_id=definition.check_id,
                category=definition.category,
                severity="critical",
                status="failed",
                title=definition.title,
                message="自检项运行时发生错误。",
                evidence={"error": str(exc)},
            )
        ]


async def iter_self_check_events(
    *,
    trigger: str,
    requested_by_user_id: int | None = None,
    check_ids: tuple[str, ...] | None = None,
    scope: SelfCheckRunScope = "full",
) -> AsyncIterator[SelfCheckRunEvent]:
    if check_ids is not None:
        for check_id in check_ids:
            validate_check_id(check_id)

    selected_check_ids = check_ids or CHECK_IDS
    run_id = secrets.token_hex(16)
    started_at = datetime.now(timezone.utc)
    findings: list[SelfCheckFindingResult] = []
    error_message: str | None = None
    retention_keep_days = 14
    result: SelfCheckRunResult | None = None

    async with _run_lock:
        yield SelfCheckRunEvent(
            type="started",
            run_id=run_id,
            trigger=trigger,
            scope=scope,
            check_id=selected_check_ids[0] if scope == "check" else None,
            total_checks=len(selected_check_ids),
            started_at=started_at,
        )

        async with get_async_session() as session:
            try:
                context = SelfCheckContext(session, config.self_check)
                retention_keep_days = context.config.retention_runs_keep_days
                enabled = context.config.enabled_check_ids()
                for check_id in selected_check_ids:
                    definition = CHECK_DEFINITIONS[check_id]
                    yield SelfCheckRunEvent(
                        type="check_started",
                        run_id=run_id,
                        trigger=trigger,
                        scope=scope,
                        check_id=check_id,
                    )
                    check_findings = await _run_definition(
                        definition, context, enabled
                    )
                    findings.extend(check_findings)
                    yield SelfCheckRunEvent(
                        type="check_finished",
                        run_id=run_id,
                        trigger=trigger,
                        scope=scope,
                        check_id=check_id,
                        findings=check_findings,
                    )
            except Exception as exc:
                logger.exception("self-check runner failed")
                error_message = str(exc)
                findings.append(
                    _finding(
                        check_id="self_check.runner",
                        category="system",
                        severity="critical",
                        status="failed",
                        title="自检运行器",
                        message="自检运行器在完成所有自检项前发生错误。",
                        evidence={"error": error_message},
                    )
                )
                yield SelfCheckRunEvent(
                    type="error",
                    run_id=run_id,
                    trigger=trigger,
                    scope=scope,
                    message=error_message,
                    findings=findings[-1:],
                )

            finished_at = datetime.now(timezone.utc)
            summary = _summarize(findings)
            result = SelfCheckRunResult(
                id=run_id,
                trigger=trigger,
                scope=scope,
                check_id=selected_check_ids[0] if scope == "check" else None,
                status=summary.status,
                started_at=started_at,
                finished_at=finished_at,
                duration_ms=int((finished_at - started_at).total_seconds() * 1000),
                summary=summary,
                findings=findings,
                error_message=error_message,
            )

            await crud.persist_run(
                session,
                result,
                requested_by_user_id=requested_by_user_id,
            )
            await crud.prune_runs(session, keep_days=retention_keep_days)

        await self_check_notification_bus.publish(result)
        yield SelfCheckRunEvent(
            type="completed",
            run_id=run_id,
            trigger=trigger,
            scope=scope,
            check_id=result.check_id,
            finished_at=result.finished_at,
            result=result,
        )


async def run_self_check(
    *,
    trigger: str,
    requested_by_user_id: int | None = None,
    check_ids: tuple[str, ...] | None = None,
    scope: SelfCheckRunScope = "full",
) -> SelfCheckRunResult:
    result: SelfCheckRunResult | None = None
    async for event in iter_self_check_events(
        trigger=trigger,
        requested_by_user_id=requested_by_user_id,
        check_ids=check_ids,
        scope=scope,
    ):
        if event.result is not None:
            result = event.result

    if result is None:
        raise RuntimeError("自检结束但没有生成结果")
    return result


__all__ = [
    "BackupJarMatch",
    "CHECK_DEFINITIONS",
    "CheckDefinition",
    "PermissionScanResult",
    "SelfCheckContext",
    "_find_backup_jars_sync",
    "_finding",
    "_scan_permission_owner_with_fd",
    "_skipped",
    "_success",
    "get_catalog",
    "iter_self_check_events",
    "run_self_check",
    "validate_check_id",
]
