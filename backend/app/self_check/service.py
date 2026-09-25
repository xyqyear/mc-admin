import asyncio
import secrets
from collections.abc import AsyncIterator, Callable, Mapping
from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from ..errors import log_safe_error, public_error_message
from ..runtime_resources import current_runtime
from . import crud
from .checks import CHECK_DEFINITIONS
from .checks.base import CheckDefinition, SelfCheckContext, SelfCheckDependencies
from .checks.base import finding as _finding
from .checks.base import skipped as _skipped
from .notifications import SelfCheckNotificationBus
from .types import (
    SelfCheckCatalogItem,
    SelfCheckFindingResult,
    SelfCheckRunEvent,
    SelfCheckRunResult,
    SelfCheckRunScope,
)


class SelfCheckService:
    def __init__(
        self, *, session_factory: Callable[[], AbstractAsyncContextManager[AsyncSession]],
        dependencies: SelfCheckDependencies, notifications: SelfCheckNotificationBus,
        definitions: Mapping[str, CheckDefinition] | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.dependencies = dependencies
        self.notifications = notifications
        self.definitions = dict(CHECK_DEFINITIONS if definitions is None else definitions)
        self.check_ids = tuple(self.definitions)
        self._run_lock = asyncio.Lock()

    def get_catalog(self) -> list[SelfCheckCatalogItem]:
        enabled = self.dependencies.configuration.self_check.enabled_check_ids()
        return [
            SelfCheckCatalogItem(
                check_id=definition.check_id,
                category=definition.category,
                title=definition.title,
                description=definition.description,
                enabled=definition.check_id in enabled,
            )
            for check_id in self.check_ids
            if (definition := self.definitions.get(check_id)) is not None
        ]

    def validate_check_id(self, check_id: str) -> CheckDefinition:
        try:
            return self.definitions[check_id]
        except KeyError as exc:
            raise ValueError(f"未知的自检项: {check_id}") from exc

    async def _run_definition(self,
        definition: CheckDefinition,
        context: SelfCheckContext,
        enabled: set[str],
    ) -> list[SelfCheckFindingResult]:
        if definition.check_id not in enabled:
            return _skipped(definition, "该自检项已被禁用。")

        try:
            return await definition.function(context)
        except Exception as exc:  # noqa: BLE001 - preserve other checks when one adapter fails
            log_safe_error(exc, f"Self-check failed ({definition.check_id})")
            return [
                _finding(
                    check_id=definition.check_id,
                    category=definition.category,
                    severity="critical",
                    status="failed",
                    title=definition.title,
                    message="自检项运行时发生错误。",
                    evidence={"error": public_error_message(exc)},
                )
            ]

    async def iter_self_check_events(self,
        *,
        trigger: str,
        requested_by_user_id: int | None = None,
        check_ids: tuple[str, ...] | None = None,
        scope: SelfCheckRunScope = "full",
    ) -> AsyncIterator[SelfCheckRunEvent]:
        if check_ids is not None:
            for check_id in check_ids:
                self.validate_check_id(check_id)

        selected_check_ids = check_ids or self.check_ids
        run_id = secrets.token_hex(16)
        started_at = datetime.now(UTC)
        findings: list[SelfCheckFindingResult] = []
        error_message: str | None = None
        retention_keep_days = 14
        result: SelfCheckRunResult | None = None

        async with self._run_lock:
            yield SelfCheckRunEvent(
                type="started",
                run_id=run_id,
                trigger=trigger,
                scope=scope,
                check_id=selected_check_ids[0] if scope == "check" else None,
                total_checks=len(selected_check_ids),
                started_at=started_at,
            )

            async with self.session_factory() as session:
                try:
                    context = SelfCheckContext(session, self.dependencies.configuration.self_check, dependencies=self.dependencies)
                    retention_keep_days = context.config.retention_runs_keep_days
                    enabled = context.config.enabled_check_ids()
                    for check_id in selected_check_ids:
                        definition = self.definitions[check_id]
                        yield SelfCheckRunEvent(
                            type="check_started",
                            run_id=run_id,
                            trigger=trigger,
                            scope=scope,
                            check_id=check_id,
                        )
                        check_findings = await self._run_definition(
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
                except Exception as exc:  # noqa: BLE001 - persist completed findings when orchestration fails
                    log_safe_error(exc, "Self-check runner failed")
                    error_message = public_error_message(exc)
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

                finished_at = datetime.now(UTC)
                summary = crud.summarize_findings(findings)
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

            await self.notifications.publish(result)
            yield SelfCheckRunEvent(
                type="completed",
                run_id=run_id,
                trigger=trigger,
                scope=scope,
                check_id=result.check_id,
                finished_at=result.finished_at,
                result=result,
            )

    async def run_self_check(self,
        *,
        trigger: str,
        requested_by_user_id: int | None = None,
        check_ids: tuple[str, ...] | None = None,
        scope: SelfCheckRunScope = "full",
    ) -> SelfCheckRunResult:
        result: SelfCheckRunResult | None = None
        async for event in self.iter_self_check_events(
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


def get_self_check_service() -> SelfCheckService:
    return current_runtime().resource("self_check_service")
