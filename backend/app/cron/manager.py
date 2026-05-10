"""APScheduler-backed cron job manager with SQLAlchemy persistence."""

import asyncio
import json
import secrets
from datetime import datetime, timezone
from typing import List, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from ..db.database import get_async_session
from ..dynamic_config.schemas import BaseConfigSchema
from ..models import CronJobStatus, ExecutionStatus
from . import crud
from .registry import cron_registry
from .types import CronJobConfig, CronJobExecutionRecord, ExecutionContext


class CronManager:
    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self._initialized = False

    async def initialize(self) -> None:
        """Start the scheduler and recover active jobs from the database."""
        if self._initialized:
            return

        self.scheduler.start()

        await self._recover_cronjobs_from_database()

        self._initialized = True

    async def shutdown(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown()

    async def create_cronjob(
        self,
        identifier: str,
        params: BaseConfigSchema,
        cron: str,
        cronjob_id: Optional[str] = None,
        name: Optional[str] = None,
        second: Optional[str] = None,
    ) -> str:
        """Create a new cron job, or revive an existing cancelled one."""
        if not cron_registry.is_registered(identifier):
            raise ValueError(f"CronJob identifier '{identifier}' not registered")

        if cronjob_id is None:
            cronjob_id = f"{identifier}_{secrets.token_urlsafe(8)}"

        cronjob_name = name or identifier

        async with get_async_session() as session:
            existing = await crud.get_cronjob(session, cronjob_id)

            if existing:
                await crud.update_cronjob(
                    session,
                    cronjob_id,
                    name=cronjob_name,
                    cron=cron,
                    second=second,
                    params_json=params.model_dump_json(),
                    status=CronJobStatus.ACTIVE,
                )
            else:
                await crud.create_cronjob(
                    session,
                    cronjob_id=cronjob_id,
                    identifier=identifier,
                    name=cronjob_name,
                    cron=cron,
                    second=second,
                    params_json=params.model_dump_json(),
                )

        await self._submit_cronjob_to_scheduler(
            cronjob_id, identifier, params, cron, second
        )

        return cronjob_id

    async def update_cronjob(
        self,
        cronjob_id: str,
        identifier: str,
        params: BaseConfigSchema,
        cron: str,
        second: Optional[str] = None,
    ) -> None:
        if not cron_registry.is_registered(identifier):
            raise ValueError(f"CronJob identifier '{identifier}' not registered")

        async with get_async_session() as session:
            existing = await crud.get_cronjob(session, cronjob_id)

            if not existing:
                raise ValueError(f"CronJob '{cronjob_id}' not found")

            current_status = existing.status

            await crud.update_cronjob(
                session,
                cronjob_id,
                identifier=identifier,
                cron=cron,
                second=second,
                params_json=params.model_dump_json(),
            )

        # Re-register the trigger only when the job is currently active.
        if current_status == CronJobStatus.ACTIVE:
            if self.scheduler.get_job(cronjob_id):
                self.scheduler.remove_job(cronjob_id)

            await self._submit_cronjob_to_scheduler(
                cronjob_id, identifier, params, cron, second
            )

    async def pause_cronjob(self, cronjob_id: str) -> None:
        async with get_async_session() as session:
            cronjob_row = await crud.get_cronjob(session, cronjob_id)

            if not cronjob_row:
                raise ValueError(f"CronJob {cronjob_id} not found")

            if not cronjob_row.status == CronJobStatus.ACTIVE:
                raise ValueError(
                    f"CronJob {cronjob_id} is not active and cannot be paused"
                )

            await crud.update_cronjob(
                session, cronjob_id, status=CronJobStatus.PAUSED
            )

        if self.scheduler.get_job(cronjob_id):
            self.scheduler.remove_job(cronjob_id)

    async def resume_cronjob(self, cronjob_id: str) -> None:
        """Resume a paused or cancelled cron job."""
        async with get_async_session() as session:
            cronjob_row = await crud.get_cronjob(session, cronjob_id)

            if not cronjob_row:
                raise ValueError(f"CronJob {cronjob_id} not found")

            if cronjob_row.status == CronJobStatus.ACTIVE:
                raise ValueError(f"CronJob {cronjob_id} is already active")

            await crud.update_cronjob(
                session, cronjob_id, status=CronJobStatus.ACTIVE
            )

            schema_cls = cron_registry.get_schema_class(cronjob_row.identifier)
            if not schema_cls:
                raise ValueError(
                    f"CronJob identifier '{cronjob_row.identifier}' not registered"
                )

            params = schema_cls.model_validate_json(cronjob_row.params_json)

        await self._submit_cronjob_to_scheduler(
            cronjob_id,
            cronjob_row.identifier,
            params,
            cronjob_row.cron,
            cronjob_row.second,
        )

    async def cancel_cronjob(self, cronjob_id: str) -> None:
        """Soft-delete a cron job."""
        async with get_async_session() as session:
            cronjob_row = await crud.get_cronjob(session, cronjob_id)

            if not cronjob_row:
                raise ValueError(f"CronJob {cronjob_id} not found")

            if cronjob_row.status == CronJobStatus.CANCELLED:
                raise ValueError(f"CronJob {cronjob_id} is already cancelled")

            await crud.update_cronjob(
                session, cronjob_id, status=CronJobStatus.CANCELLED
            )

        if self.scheduler.get_job(cronjob_id):
            self.scheduler.remove_job(cronjob_id)

    async def get_cronjob_config(self, cronjob_id: str) -> Optional[CronJobConfig]:
        async with get_async_session() as session:
            cronjob_row = await crud.get_cronjob(session, cronjob_id)

            if not cronjob_row:
                return None

            schema_cls = cron_registry.get_schema_class(cronjob_row.identifier)
            if not schema_cls:
                return None

            params = schema_cls.model_validate_json(cronjob_row.params_json)

            return CronJobConfig(
                cronjob_id=cronjob_row.cronjob_id,
                identifier=cronjob_row.identifier,
                name=cronjob_row.name,
                cron=cronjob_row.cron,
                second=cronjob_row.second,
                params=params,
                execution_count=cronjob_row.execution_count,
                status=cronjob_row.status,
                created_at=cronjob_row.created_at,
                updated_at=cronjob_row.updated_at,
            )

    async def get_all_cronjobs(
        self,
        identifier: Optional[str] = None,
        status: Optional[List[CronJobStatus]] = None,
        name: Optional[str] = None,
    ) -> List[CronJobConfig]:
        async with get_async_session() as session:
            cronjob_rows = await crud.get_all_cronjobs(
                session, identifier=identifier, status=status, name=name
            )

            configs = []
            for cronjob_row in cronjob_rows:
                schema_cls = cron_registry.get_schema_class(cronjob_row.identifier)
                if not schema_cls:
                    continue

                try:
                    params = schema_cls.model_validate_json(cronjob_row.params_json)
                except Exception:
                    continue

                configs.append(
                    CronJobConfig(
                        cronjob_id=cronjob_row.cronjob_id,
                        identifier=cronjob_row.identifier,
                        name=cronjob_row.name,
                        cron=cronjob_row.cron,
                        second=cronjob_row.second,
                        params=params,
                        execution_count=cronjob_row.execution_count,
                        status=cronjob_row.status,
                        created_at=cronjob_row.created_at,
                        updated_at=cronjob_row.updated_at,
                    )
                )

            return configs

    async def get_execution_history(
        self, cronjob_id: str, limit: int = 50
    ) -> List[CronJobExecutionRecord]:
        async with get_async_session() as session:
            cronjob_row = await crud.get_cronjob(session, cronjob_id)

            if not cronjob_row:
                raise ValueError(f"CronJob {cronjob_id} not found")

            executions = await crud.get_execution_history(
                session, cronjob_id, limit
            )

            return [
                CronJobExecutionRecord(
                    cronjob_id=ex.cronjob_id,
                    execution_id=ex.execution_id,
                    started_at=ex.started_at,
                    ended_at=ex.ended_at,
                    duration_ms=ex.duration_ms,
                    status=ex.status,
                    messages=json.loads(ex.messages_json) if ex.messages_json else [],
                )
                for ex in executions
            ]

    async def get_next_run_time(self, cronjob_id: str) -> Optional[datetime]:
        """Raises ``ValueError`` if the job is missing or not active."""
        async with get_async_session() as session:
            cronjob_row = await crud.get_cronjob(session, cronjob_id)

            if not cronjob_row:
                raise ValueError(f"CronJob {cronjob_id} not found")

            if cronjob_row.status != CronJobStatus.ACTIVE:
                raise ValueError(f"CronJob {cronjob_id} is not in active state")

        scheduler_job = self.scheduler.get_job(cronjob_id)
        if scheduler_job is None:
            raise ValueError(f"CronJob {cronjob_id} not found in scheduler")

        return scheduler_job.next_run_time

    async def _submit_cronjob_to_scheduler(
        self,
        cronjob_id: str,
        identifier: str,
        params: BaseConfigSchema,
        cron: str,
        second: Optional[str] = None,
    ) -> None:
        cronjob_registration = cron_registry.get_cronjob(identifier)
        if not cronjob_registration:
            raise ValueError(f"CronJob identifier '{identifier}' not registered")

        cronjob_function = cronjob_registration.function

        cron_parts = cron.strip().split()
        if len(cron_parts) != 5:
            raise ValueError(
                "Cron expression must have exactly 5 fields (minute hour day month day_of_week)"
            )

        trigger = CronTrigger(
            second=second,
            minute=cron_parts[0],
            hour=cron_parts[1],
            day=cron_parts[2],
            month=cron_parts[3],
            day_of_week=cron_parts[4],
        )

        self.scheduler.add_job(
            self._execute_cronjob_wrapper,
            trigger=trigger,
            args=[cronjob_id, identifier, params, cronjob_function],
            id=cronjob_id,
            replace_existing=True,
        )

    async def _execute_cronjob_wrapper(
        self,
        cronjob_id: str,
        identifier: str,
        params: BaseConfigSchema,
        cronjob_function,
    ) -> None:
        """Run ``cronjob_function`` with execution context, recording the outcome."""
        timestamp = int(datetime.now(timezone.utc).timestamp() * 1000)
        random_suffix = secrets.token_urlsafe(4)
        execution_id = f"{timestamp}_{random_suffix}"

        context = ExecutionContext(
            cronjob_id=cronjob_id,
            identifier=identifier,
            execution_id=execution_id,
            params=params,
            started_at=datetime.now(timezone.utc),
            status=ExecutionStatus.RUNNING,
        )

        try:
            await cronjob_function(context)
            context.status = ExecutionStatus.COMPLETED
        except asyncio.CancelledError:
            context.status = ExecutionStatus.CANCELLED
            context.log("CronJob execution was cancelled")
            raise
        except Exception as e:
            context.status = ExecutionStatus.FAILED
            context.log(f"CronJob execution failed: {str(e)}")
        finally:
            context.ended_at = datetime.now(timezone.utc)
            if context.ended_at and context.started_at:
                context.duration_ms = int(
                    (context.ended_at - context.started_at).total_seconds() * 1000
                )

            async with get_async_session() as session:
                await crud.create_execution_record(
                    session, context.to_execution_record()
                )
            async with get_async_session() as session:
                await crud.increment_execution_count(session, cronjob_id)

    async def _recover_cronjobs_from_database(self) -> None:
        async with get_async_session() as session:
            active_cronjobs = await crud.get_cronjobs_by_status(
                session, CronJobStatus.ACTIVE
            )

            for cronjob_row in active_cronjobs:
                schema_cls = cron_registry.get_schema_class(cronjob_row.identifier)
                if not schema_cls:
                    continue

                try:
                    params = schema_cls.model_validate_json(cronjob_row.params_json)
                except Exception as e:
                    print(f"Failed to recover cron job {cronjob_row.cronjob_id}: {e}")
                    continue

                await self._submit_cronjob_to_scheduler(
                    cronjob_row.cronjob_id,
                    cronjob_row.identifier,
                    params,
                    cronjob_row.cron,
                    cronjob_row.second,
                )
