"""
Cron Manager - Core cron job management and scheduling functionality.
"""

import asyncio
import json
import secrets
from datetime import datetime, timezone
from typing import List, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select, update

from ..db.database import get_async_session
from ..dynamic_config.schemas import BaseConfigSchema
from ..models import CronJob, CronJobExecution, CronJobStatus, ExecutionStatus
from .registry import cron_registry
from .types import CronJobConfig, CronJobExecutionRecord, ExecutionContext


class CronManager:
    """
    Core cron job management class.

    Handles cron job creation, scheduling, execution monitoring, and lifecycle
    management using APScheduler for scheduling and SQLAlchemy for persistence.
    """

    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self._initialized = False

    async def initialize(self) -> None:
        """
        Initialize the cron manager and recover cron jobs from database.
        """
        if self._initialized:
            return

        # Start the scheduler
        self.scheduler.start()

        # Recover cron jobs from database
        await self._recover_cronjobs_from_database()

        self._initialized = True

    async def shutdown(self) -> None:
        """
        Shutdown the cron manager and scheduler.
        """
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
        """
        Create a new cron job or recover an existing cancelled cron job.

        Args:
            identifier: CronJob identifier (must be registered)
            params: CronJob parameters (BaseConfigSchema instance)
            cron: Cron expression for scheduling (5 fields)
            cronjob_id: Optional cron job ID (auto-generated if not provided)
            name: Optional cron job name (defaults to identifier)
            second: Optional second field for precise scheduling

        Returns:
            CronJob ID of the created/recovered cron job

        Raises:
            ValueError: If identifier is not registered
        """
        # Validate identifier is registered
        if not cron_registry.is_registered(identifier):
            raise ValueError(f"CronJob identifier '{identifier}' not registered")

        # Generate or use provided cronjob_id
        if cronjob_id is None:
            cronjob_id = f"{identifier}_{secrets.token_urlsafe(8)}"

        cronjob_name = name or identifier

        async with get_async_session() as session:
            # Check if cron job already exists (using cronjob_id field, not primary key)
            result = await session.execute(
                select(CronJob).where(CronJob.cronjob_id == cronjob_id)
            )
            existing_cronjob = result.scalar_one_or_none()

            if existing_cronjob:
                # Update existing cron job (especially if it was cancelled)
                await session.execute(
                    update(CronJob)
                    .where(CronJob.cronjob_id == cronjob_id)
                    .values(
                        name=cronjob_name,
                        cron=cron,
                        second=second,
                        params_json=params.model_dump_json(),
                        status=CronJobStatus.ACTIVE,
                        updated_at=datetime.now(timezone.utc),
                    )
                )
            else:
                # Create new cron job
                new_cronjob = CronJob(
                    cronjob_id=cronjob_id,
                    identifier=identifier,
                    name=cronjob_name,
                    cron=cron,
                    second=second,
                    params_json=params.model_dump_json(),
                    status=CronJobStatus.ACTIVE,
                )
                session.add(new_cronjob)

            await session.commit()

        # Submit to scheduler
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
        """
        Update an existing cron job configuration.

        Args:
            cronjob_id: The ID of the cron job to update
            identifier: The cron job type identifier
            params: Job-specific parameters (validated against registered schema)
            cron: Standard cron expression (5 fields: minute hour day month weekday)
            second: Optional second field for more precise scheduling

        Raises:
            ValueError: If identifier is not registered or cron job not found
        """
        # Validate identifier is registered
        if not cron_registry.is_registered(identifier):
            raise ValueError(f"CronJob identifier '{identifier}' not registered")

        async with get_async_session() as session:
            # Check if cron job exists
            result = await session.execute(
                select(CronJob).where(CronJob.cronjob_id == cronjob_id)
            )
            existing_cronjob = result.scalar_one_or_none()

            if not existing_cronjob:
                raise ValueError(f"CronJob '{cronjob_id}' not found")

            # Get current status to determine if we need to reschedule
            current_status = existing_cronjob.status

            # Update the cron job configuration
            await session.execute(
                update(CronJob)
                .where(CronJob.cronjob_id == cronjob_id)
                .values(
                    identifier=identifier,
                    cron=cron,
                    second=second,
                    params_json=params.model_dump_json(),
                    updated_at=datetime.now(timezone.utc),
                )
            )

            await session.commit()

        # If the job is currently active, remove from scheduler and re-add with new config
        if current_status == CronJobStatus.ACTIVE:
            # Remove old job from scheduler
            if self.scheduler.get_job(cronjob_id):
                self.scheduler.remove_job(cronjob_id)

            # Re-submit with new configuration
            await self._submit_cronjob_to_scheduler(
                cronjob_id, identifier, params, cron, second
            )

    async def pause_cronjob(self, cronjob_id: str) -> None:
        """
        Pause a cron job.

        Args:
            cronjob_id: CronJob ID to pause
        """
        async with get_async_session() as session:
            # Check if cron job exists first
            result = await session.execute(
                select(CronJob).where(CronJob.cronjob_id == cronjob_id)
            )
            cronjob_row = result.scalar_one_or_none()

            if not cronjob_row:
                raise ValueError(f"CronJob {cronjob_id} not found")

            if not cronjob_row.status == CronJobStatus.ACTIVE:
                raise ValueError(
                    f"CronJob {cronjob_id} is not active and cannot be paused"
                )

            await session.execute(
                update(CronJob)
                .where(CronJob.cronjob_id == cronjob_id)
                .values(
                    status=CronJobStatus.PAUSED, updated_at=datetime.now(timezone.utc)
                )
            )
            await session.commit()

        # Remove from scheduler
        if self.scheduler.get_job(cronjob_id):
            self.scheduler.remove_job(cronjob_id)

    async def resume_cronjob(self, cronjob_id: str) -> None:
        """
        Resume a paused or cancelled cron job.

        Args:
            cronjob_id: CronJob ID to resume
        """
        async with get_async_session() as session:
            # Get cron job details
            result = await session.execute(
                select(CronJob).where(CronJob.cronjob_id == cronjob_id)
            )
            cronjob_row = result.scalar_one_or_none()

            if not cronjob_row:
                raise ValueError(f"CronJob {cronjob_id} not found")

            # Check if the job can be resumed (not already active)
            if cronjob_row.status == CronJobStatus.ACTIVE:
                raise ValueError(f"CronJob {cronjob_id} is already active")

            # Update status
            await session.execute(
                update(CronJob)
                .where(CronJob.cronjob_id == cronjob_id)
                .values(
                    status=CronJobStatus.ACTIVE, updated_at=datetime.now(timezone.utc)
                )
            )
            await session.commit()

            # Get schema class and deserialize params
            schema_cls = cron_registry.get_schema_class(cronjob_row.identifier)
            if not schema_cls:
                raise ValueError(
                    f"CronJob identifier '{cronjob_row.identifier}' not registered"
                )

            params = schema_cls.model_validate_json(cronjob_row.params_json)

        # Re-submit to scheduler
        await self._submit_cronjob_to_scheduler(
            cronjob_id,
            cronjob_row.identifier,
            params,
            cronjob_row.cron,
            cronjob_row.second,
        )

    async def cancel_cronjob(self, cronjob_id: str) -> None:
        """
        Cancel a cron job (soft delete).

        Args:
            cronjob_id: CronJob ID to cancel
        """
        async with get_async_session() as session:
            # Check if cron job exists first
            result = await session.execute(
                select(CronJob).where(CronJob.cronjob_id == cronjob_id)
            )
            cronjob_row = result.scalar_one_or_none()

            if not cronjob_row:
                raise ValueError(f"CronJob {cronjob_id} not found")

            if cronjob_row.status == CronJobStatus.CANCELLED:
                raise ValueError(f"CronJob {cronjob_id} is already cancelled")

            await session.execute(
                update(CronJob)
                .where(CronJob.cronjob_id == cronjob_id)
                .values(
                    status=CronJobStatus.CANCELLED,
                    updated_at=datetime.now(timezone.utc),
                )
            )
            await session.commit()

        # Remove from scheduler
        if self.scheduler.get_job(cronjob_id):
            self.scheduler.remove_job(cronjob_id)

    async def get_cronjob_config(self, cronjob_id: str) -> Optional[CronJobConfig]:
        """
        Get cron job configuration.

        Args:
            cronjob_id: CronJob ID

        Returns:
            CronJobConfig instance or None if not found
        """
        async with get_async_session() as session:
            result = await session.execute(
                select(CronJob).where(CronJob.cronjob_id == cronjob_id)
            )
            cronjob_row = result.scalar_one_or_none()

            if not cronjob_row:
                return None

            # Get schema class and deserialize params
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
        """
        Get all cron job configurations with optional filtering.

        Args:
            identifier: Optional job type identifier to filter by
            status: Optional list of job statuses to filter by
            name: Optional job name to filter by

        Returns:
            List of CronJobConfig instances
        """
        async with get_async_session() as session:
            # Build query with filters
            query = select(CronJob)

            # Apply identifier filter
            if identifier:
                query = query.where(CronJob.identifier == identifier)

            # Apply status filter
            if status:
                query = query.where(CronJob.status.in_(status))

            # Apply name filter (case-insensitive partial match)
            if name:
                query = query.where(CronJob.name.ilike(f"%{name}%"))

            # Order by creation date (newest first)
            query = query.order_by(CronJob.created_at.desc())

            result = await session.execute(query)
            cronjob_rows = result.scalars().all()

            configs = []
            for cronjob_row in cronjob_rows:
                # Get schema class and deserialize params
                schema_cls = cron_registry.get_schema_class(cronjob_row.identifier)
                if not schema_cls:
                    # Skip jobs with unknown identifiers
                    continue

                try:
                    params = schema_cls.model_validate_json(cronjob_row.params_json)
                except Exception:
                    # Skip jobs with invalid params
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
        """
        Get cron job execution history.

        Args:
            cronjob_id: CronJob ID
            limit: Maximum number of records to return

        Returns:
            List of CronJobExecutionRecord dataclasses
        """
        async with get_async_session() as session:
            # Check if cron job exists first
            cronjob_result = await session.execute(
                select(CronJob).where(CronJob.cronjob_id == cronjob_id)
            )
            cronjob_row = cronjob_result.scalar_one_or_none()

            if not cronjob_row:
                raise ValueError(f"CronJob {cronjob_id} not found")

            result = await session.execute(
                select(CronJobExecution)
                .where(CronJobExecution.cronjob_id == cronjob_id)
                .order_by(CronJobExecution.started_at.desc())
                .limit(limit)
            )
            executions = result.scalars().all()

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
        """
        Get the next scheduled run time for a cron job.

        Args:
            cronjob_id: CronJob ID

        Returns:
            Next run time as datetime or None if job not found/not running

        Raises:
            ValueError: If cron job not found or not in active state
        """
        async with get_async_session() as session:
            # Check if cron job exists and get its status
            result = await session.execute(
                select(CronJob).where(CronJob.cronjob_id == cronjob_id)
            )
            cronjob_row = result.scalar_one_or_none()

            if not cronjob_row:
                raise ValueError(f"CronJob {cronjob_id} not found")

            # Only return next run time if job is active
            if cronjob_row.status != CronJobStatus.ACTIVE:
                raise ValueError(f"CronJob {cronjob_id} is not in active state")

        # Get the job from scheduler
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
        """
        Submit a cron job to the APScheduler.

        Args:
            cronjob_id: CronJob ID
            identifier: CronJob identifier
            params: CronJob parameters
            cron: Cron expression (5 fields: minute hour day month day_of_week)
            second: Optional second field for more precise scheduling
        """
        # Get the cron job function
        cronjob_registration = cron_registry.get_cronjob(identifier)
        if not cronjob_registration:
            raise ValueError(f"CronJob identifier '{identifier}' not registered")

        cronjob_function = cronjob_registration.function

        # Parse cron expression and validate
        cron_parts = cron.strip().split()
        if len(cron_parts) != 5:
            raise ValueError(
                "Cron expression must have exactly 5 fields (minute hour day month day_of_week)"
            )

        # Create cron trigger with optional second parameter
        trigger = CronTrigger(
            second=second,
            minute=cron_parts[0],
            hour=cron_parts[1],
            day=cron_parts[2],
            month=cron_parts[3],
            day_of_week=cron_parts[4],
        )

        # Add job to scheduler
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
        """
        CronJob execution wrapper that handles context management and recording.

        Args:
            cronjob_id: CronJob ID
            identifier: CronJob identifier
            params: CronJob parameters
            cronjob_function: The actual cron job function to execute
        """
        # Use timestamp + random to avoid collisions
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
            # Execute the cron job function
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
            # Record execution completion
            context.ended_at = datetime.now(timezone.utc)
            if context.ended_at and context.started_at:
                context.duration_ms = int(
                    (context.ended_at - context.started_at).total_seconds() * 1000
                )

            # Save execution record
            await self._record_execution(context)

            # Update cron job execution count
            await self._increment_execution_count(cronjob_id)

    async def _record_execution(self, context: ExecutionContext) -> None:
        """
        Record cron job execution to database.

        Args:
            context: Execution context
        """
        async with get_async_session() as session:
            execution = CronJobExecution(**context.to_execution_record())
            session.add(execution)
            await session.commit()

    async def _increment_execution_count(self, cronjob_id: str) -> None:
        """
        Increment cron job execution count.

        Args:
            cronjob_id: CronJob ID
        """
        async with get_async_session() as session:
            await session.execute(
                update(CronJob)
                .where(CronJob.cronjob_id == cronjob_id)
                .values(execution_count=CronJob.execution_count + 1)
            )
            await session.commit()

    async def _recover_cronjobs_from_database(self) -> None:
        """
        Recover active cron jobs from database on startup.
        """
        async with get_async_session() as session:
            result = await session.execute(
                select(CronJob).where(CronJob.status == CronJobStatus.ACTIVE)
            )
            active_cronjobs = result.scalars().all()

            for cronjob_row in active_cronjobs:
                schema_cls = cron_registry.get_schema_class(cronjob_row.identifier)
                if not schema_cls:
                    continue

                try:
                    params = schema_cls.model_validate_json(cronjob_row.params_json)
                except Exception as e:
                    # Log error but continue with other cron jobs
                    print(f"Failed to recover cron job {cronjob_row.cronjob_id}: {e}")
                    continue

                await self._submit_cronjob_to_scheduler(
                    cronjob_row.cronjob_id,
                    cronjob_row.identifier,
                    params,
                    cronjob_row.cron,
                    cronjob_row.second,
                )
