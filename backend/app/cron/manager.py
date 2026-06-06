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
from ..logger import logger
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
        await self._ensure_system_cronjobs()

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
        is_system: bool = False,
    ) -> str:
        """Create a new cron job, or revive an existing cancelled one."""
        registration = cron_registry.get_cronjob(identifier)
        if not registration:
            raise ValueError(f"定时任务类型 '{identifier}' 未注册")
        if registration.is_system and not is_system:
            raise ValueError(f"系统定时任务类型 '{identifier}' 不能手动创建")

        if cronjob_id is None:
            cronjob_id = f"{identifier}_{secrets.token_urlsafe(8)}"

        self._build_cron_trigger(cron, second)
        cronjob_name = name or identifier

        async with get_async_session() as session:
            existing = await crud.get_cronjob(session, cronjob_id)

            if existing:
                if existing.is_system and existing.identifier != identifier:
                    raise ValueError("系统定时任务不能修改任务类型")

                await crud.update_cronjob(
                    session,
                    cronjob_id,
                    name=cronjob_name,
                    cron=cron,
                    second=second,
                    params_json=params.model_dump_json(),
                    status=CronJobStatus.ACTIVE,
                    is_system=is_system or existing.is_system,
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
                    is_system=is_system,
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
        name: Optional[str] = None,
    ) -> None:
        if not cron_registry.is_registered(identifier):
            raise ValueError(f"定时任务类型 '{identifier}' 未注册")

        self._build_cron_trigger(cron, second)

        async with get_async_session() as session:
            existing = await crud.get_cronjob(session, cronjob_id)

            if not existing:
                raise ValueError(f"定时任务 '{cronjob_id}' 不存在")

            if existing.is_system and existing.identifier != identifier:
                raise ValueError("系统定时任务不能修改任务类型")

            current_status = existing.status

            await crud.update_cronjob(
                session,
                cronjob_id,
                identifier=identifier,
                name=name if name is not None else existing.name,
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
                raise ValueError(f"定时任务 '{cronjob_id}' 不存在")

            if cronjob_row.is_system:
                raise ValueError(f"系统定时任务 '{cronjob_id}' 不能暂停")

            if not cronjob_row.status == CronJobStatus.ACTIVE:
                raise ValueError(f"定时任务 '{cronjob_id}' 未处于运行中，不能暂停")

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
                raise ValueError(f"定时任务 '{cronjob_id}' 不存在")

            if cronjob_row.status == CronJobStatus.ACTIVE:
                raise ValueError(f"定时任务 '{cronjob_id}' 已在运行中")

            await crud.update_cronjob(
                session, cronjob_id, status=CronJobStatus.ACTIVE
            )

            schema_cls = cron_registry.get_schema_class(cronjob_row.identifier)
            if not schema_cls:
                raise ValueError(f"定时任务类型 '{cronjob_row.identifier}' 未注册")

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
                raise ValueError(f"定时任务 '{cronjob_id}' 不存在")

            if cronjob_row.is_system:
                raise ValueError(f"系统定时任务 '{cronjob_id}' 不能取消")

            if cronjob_row.status == CronJobStatus.CANCELLED:
                raise ValueError(f"定时任务 '{cronjob_id}' 已取消")

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
                is_system=cronjob_row.is_system,
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
                        is_system=cronjob_row.is_system,
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
                raise ValueError(f"定时任务 '{cronjob_id}' 不存在")

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
                raise ValueError(f"定时任务 '{cronjob_id}' 不存在")

            if cronjob_row.status != CronJobStatus.ACTIVE:
                raise ValueError(f"定时任务 '{cronjob_id}' 未处于运行中")

        scheduler_job = self.scheduler.get_job(cronjob_id)
        if scheduler_job is None:
            raise ValueError(f"调度器中不存在定时任务 '{cronjob_id}'")

        return scheduler_job.next_run_time

    async def _submit_cronjob_to_scheduler(
        self,
        cronjob_id: str,
        identifier: str,
        params: BaseConfigSchema,
        cron: str,
        second: Optional[str] = None,
    ) -> None:
        trigger = self._build_cron_trigger(cron, second)

        cronjob_registration = cron_registry.get_cronjob(identifier)
        if not cronjob_registration:
            raise ValueError(f"定时任务类型 '{identifier}' 未注册")

        cronjob_function = cronjob_registration.function

        self.scheduler.add_job(
            self._execute_cronjob_wrapper,
            trigger=trigger,
            args=[cronjob_id, identifier, params, cronjob_function],
            id=cronjob_id,
            replace_existing=True,
        )

    def _build_cron_trigger(
        self,
        cron: str,
        second: Optional[str] = None,
    ) -> CronTrigger:
        cron_parts = cron.strip().split()
        if len(cron_parts) != 5:
            raise ValueError(
                "Cron 表达式必须包含 5 个字段（分钟 小时 日期 月份 星期）"
            )

        return CronTrigger(
            second=second,
            minute=cron_parts[0],
            hour=cron_parts[1],
            day=cron_parts[2],
            month=cron_parts[3],
            day_of_week=cron_parts[4],
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
            context.log("定时任务执行已取消")
            raise
        except Exception as e:
            context.status = ExecutionStatus.FAILED
            context.log(f"定时任务执行失败: {str(e)}")
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
                    logger.warning(
                        "failed to recover cron job %s: %s",
                        cronjob_row.cronjob_id,
                        e,
                    )
                    continue

                try:
                    await self._submit_cronjob_to_scheduler(
                        cronjob_row.cronjob_id,
                        cronjob_row.identifier,
                        params,
                        cronjob_row.cron,
                        cronjob_row.second,
                    )
                except Exception as e:
                    logger.warning(
                        "failed to schedule recovered cron job %s: %s",
                        cronjob_row.cronjob_id,
                        e,
                    )
                    continue

    async def _ensure_system_cronjobs(self) -> None:
        """Create and repair code-defined system cron jobs."""
        for identifier, registration in cron_registry.get_all_cronjobs().items():
            if not registration.is_system:
                continue

            if registration.default_cron is None:
                raise ValueError(
                    f"系统定时任务 '{identifier}' 必须定义默认 Cron 表达式"
                )
            if registration.default_params is None:
                raise ValueError(
                    f"系统定时任务 '{identifier}' 必须定义默认参数"
                )

            cronjob_id = f"system:{identifier}"
            async with get_async_session() as session:
                existing = await crud.get_cronjob(session, cronjob_id)

                if existing is None:
                    await crud.create_cronjob(
                        session,
                        cronjob_id=cronjob_id,
                        identifier=identifier,
                        name=registration.default_name or identifier,
                        cron=registration.default_cron,
                        second=registration.default_second,
                        params_json=registration.default_params.model_dump_json(),
                        is_system=True,
                    )
                    await self._submit_cronjob_to_scheduler(
                        cronjob_id,
                        identifier,
                        registration.default_params,
                        registration.default_cron,
                        registration.default_second,
                    )
                    continue

                if existing.identifier != identifier:
                    raise ValueError(
                        f"系统定时任务 '{cronjob_id}' 的任务类型是 "
                        f"'{existing.identifier}'，期望为 '{identifier}'"
                    )

                if not existing.is_system:
                    await crud.update_cronjob(session, cronjob_id, is_system=True)

                if existing.status != CronJobStatus.ACTIVE:
                    await crud.update_cronjob(
                        session, cronjob_id, status=CronJobStatus.ACTIVE
                    )
                    existing.status = CronJobStatus.ACTIVE

                if self.scheduler.get_job(cronjob_id) is None:
                    try:
                        params = registration.schema_cls.model_validate_json(
                            existing.params_json
                        )
                    except Exception as exc:
                        logger.warning(
                            "repairing system cron job %s params from defaults: %s",
                            cronjob_id,
                            exc,
                        )
                        params = registration.default_params
                        await crud.update_cronjob(
                            session,
                            cronjob_id,
                            params_json=params.model_dump_json(),
                        )
                    cron = existing.cron
                    second = existing.second
                    try:
                        self._build_cron_trigger(cron, second)
                    except Exception as exc:
                        logger.warning(
                            "repairing system cron job %s schedule from defaults: %s",
                            cronjob_id,
                            exc,
                        )
                        cron = registration.default_cron
                        second = registration.default_second
                        await crud.update_cronjob(
                            session,
                            cronjob_id,
                            cron=cron,
                            second=second,
                        )
                    await self._submit_cronjob_to_scheduler(
                        cronjob_id,
                        existing.identifier,
                        params,
                        cron,
                        second,
                    )
