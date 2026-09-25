"""APScheduler-backed cron job manager with SQLAlchemy persistence."""

import asyncio
import json
import secrets
from datetime import UTC, datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.cron.models import CronJobStatus, ExecutionStatus

from ..db.database import get_async_session
from ..dynamic_config.schemas import BaseConfigSchema
from ..errors import log_safe_error, public_error_message
from ..logger import get_logger
from ..operations.context import record_phase
from ..operations.coordinator import ResourceClaim, ResourceKind
from ..operations.execution import operation_scope
from ..operations.finalization import finalize
from ..operations.journal_types import TERMINAL_STATES, OperationState
from . import crud
from .bindings import (
    RESTART_PURPOSE,
    managed_binding_problem,
    read_cron_params,
    validate_managed_update,
)
from .models import CronJob
from .registration import definition_version, retained_params
from .registry import get_cron_registry
from .types import CronJobConfig, CronJobExecutionRecord, ExecutionContext
from .weekdays import normalize_crontab_weekday


class CronManager:
    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self._initialized = False
        self._registration_errors: dict[str, str] = {}
        self._configuration_lock = asyncio.Lock()
        self._executions: set[asyncio.Task] = set()

    async def initialize(self) -> None:
        """Start the scheduler and recover active jobs from the database."""
        try:
            async with self._configuration_lock:
                if self._initialized:
                    return
                self.scheduler.start(paused=True)
                await self._recover_cronjobs_from_database()
                await self._ensure_system_cronjobs()
                self._initialized = True
                self.scheduler.resume()
        except BaseException:
            await self.shutdown()
            raise

    async def shutdown(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown()
        workers = [task for task in self._executions if not task.done()]
        for task in workers:
            task.cancel()
        if workers:
            await finalize(asyncio.gather(*workers, return_exceptions=True))
        self._initialized = False

    async def create_cronjob(
        self,
        identifier: str,
        params: BaseConfigSchema,
        cron: str,
        cronjob_id: str | None = None,
        name: str | None = None,
        second: str | None = None,
        is_system: bool = False,
        *,
        managed_server_generation: int | None = None,
    ) -> str:
        """Create a new cron job, or revive an existing cancelled one."""
        async with self._configuration_lock:
            registration = get_cron_registry().get_cronjob(identifier)
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
                    await validate_managed_update(session, existing, identifier, params)
                    if managed_server_generation is not None and existing.managed_server_generation != managed_server_generation:
                        raise ValueError("受管计划不能转移到其他服务器实例")
                    if existing.is_system and existing.identifier != identifier:
                        raise ValueError("系统定时任务不能修改任务类型")

                    await crud.update_cronjob(
                        session,
                        cronjob_id,
                        identifier=identifier,
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
                        managed_server_generation=managed_server_generation,
                        managed_purpose=RESTART_PURPOSE if managed_server_generation is not None else None,
                    )

            await self._submit_cronjob_to_scheduler(
                cronjob_id, identifier, params, cron, second
            )

            return cronjob_id

    async def create_managed_restart_schedule(
        self, server_id: str, params: BaseConfigSchema, cron: str, name: str,
    ) -> str:
        async with get_async_session() as session:
            generation = await crud.get_active_server_generation(session, server_id)
        try:
            return await self.create_cronjob(
                "restart_server", params, cron, name=name, managed_server_generation=generation,
            )
        except IntegrityError as exc:
            raise ValueError("当前服务器已存在受管重启计划，请刷新后重试") from exc

    async def update_cronjob(
        self,
        cronjob_id: str,
        identifier: str,
        params: BaseConfigSchema,
        cron: str,
        second: str | None = None,
        name: str | None = None,
    ) -> None:
        async with self._configuration_lock:
            if not get_cron_registry().is_registered(identifier):
                raise ValueError(f"定时任务类型 '{identifier}' 未注册")

            self._build_cron_trigger(cron, second)

            async with get_async_session() as session:
                existing = await crud.get_cronjob(session, cronjob_id)

                if not existing:
                    raise ValueError(f"定时任务 '{cronjob_id}' 不存在")

                await validate_managed_update(session, existing, identifier, params)

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
        async with self._configuration_lock:
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
        async with self._configuration_lock:
            async with get_async_session() as session:
                cronjob_row = await crud.get_cronjob(session, cronjob_id)

                if not cronjob_row:
                    raise ValueError(f"定时任务 '{cronjob_id}' 不存在")

                if cronjob_row.status == CronJobStatus.ACTIVE and self.scheduler.get_job(cronjob_id) is not None and cronjob_id not in self._registration_errors:
                    raise ValueError(f"定时任务 '{cronjob_id}' 已在运行中")

                problem = await managed_binding_problem(session, cronjob_row)
                if problem:
                    raise ValueError(f"{problem}；不能恢复该计划，请核对后取消并重新创建")

                schema_cls = get_cron_registry().get_schema_class(cronjob_row.identifier)
                if not schema_cls:
                    raise ValueError(f"定时任务类型 '{cronjob_row.identifier}' 未注册")

                params = read_cron_params(cronjob_row, schema_cls)
                self._build_cron_trigger(cronjob_row.cron, cronjob_row.second)
                await crud.update_cronjob(session, cronjob_id, status=CronJobStatus.ACTIVE)

            await self._submit_cronjob_to_scheduler(
                cronjob_id,
                cronjob_row.identifier,
                params,
                cronjob_row.cron,
                cronjob_row.second,
            )

    async def cancel_cronjob(self, cronjob_id: str) -> None:
        """Soft-delete a cron job."""
        async with self._configuration_lock:
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

    async def get_cronjob_config(self, cronjob_id: str) -> CronJobConfig | None:
        async with get_async_session() as session:
            cronjob_row = await crud.get_cronjob(session, cronjob_id)

            if not cronjob_row:
                return None

            return await self._project_config(session, cronjob_row)

    async def _project_config(self, session: AsyncSession, job: CronJob) -> CronJobConfig:
        error = self._registration_errors.get(job.cronjob_id)
        problem = await managed_binding_problem(session, job)
        schema_cls = get_cron_registry().get_schema_class(job.identifier)
        params = retained_params(job.params_json)
        if schema_cls is None:
            error = "定时任务类型未注册，请核对任务配置"
        else:
            try:
                params = read_cron_params(job, schema_cls)
                self._build_cron_trigger(job.cron, job.second)
            except (ValueError, TypeError):
                error = "定时任务配置无效，请修改后重新启用"
        state = "pending"
        if job.status != CronJobStatus.ACTIVE:
            state = "inactive"
        elif problem:
            state, error = "blocked", problem
        elif error:
            state = "failed"
        else:
            scheduled = self.scheduler.get_job(job.cronjob_id)
            if scheduled is not None and self._initialized and not scheduled.pending:
                current = definition_version(job.identifier, job.params_json, job.cron, job.second)
                if scheduled.kwargs.get("definition_token") == current:
                    state = "registered"
        return CronJobConfig(
            cronjob_id=job.cronjob_id, identifier=job.identifier, name=job.name,
            cron=job.cron, second=job.second, params=params,
            managed_server_generation=job.managed_server_generation,
            managed_purpose=job.managed_purpose, managed_binding_issue=job.managed_binding_issue,
            execution_count=job.execution_count, is_system=job.is_system, status=job.status,
            registration_status=state, registration_error=error,
            created_at=job.created_at, updated_at=job.updated_at,
        )

    async def get_managed_restart_schedule(self, server_id: str) -> CronJobConfig | None:
        async with get_async_session() as session:
            job = await crud.get_managed_restart_cronjob(session, server_id)
            if job is not None:
                problem = await managed_binding_problem(session, job)
                if problem:
                    raise ValueError(problem)
            job_id = job.cronjob_id if job is not None else None
        return await self.get_cronjob_config(job_id) if job_id is not None else None

    async def get_all_cronjobs(
        self,
        identifier: str | None = None,
        status: list[CronJobStatus] | None = None,
        name: str | None = None,
    ) -> list[CronJobConfig]:
        async with get_async_session() as session:
            cronjob_rows = await crud.get_all_cronjobs(
                session, identifier=identifier, status=status, name=name
            )

            return [await self._project_config(session, row) for row in cronjob_rows]

    async def get_execution_history(
        self, cronjob_id: str, limit: int = 50
    ) -> list[CronJobExecutionRecord]:
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

    async def get_next_run_time(self, cronjob_id: str) -> datetime | None:
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
        if cronjob_id in self._registration_errors or scheduler_job.kwargs.get("definition_token") != definition_version(
            cronjob_row.identifier, cronjob_row.params_json, cronjob_row.cron, cronjob_row.second,
        ):
            raise ValueError("定时任务未成功注册，不能提供下次运行时间")

        return getattr(scheduler_job, "next_run_time", None)

    async def _submit_cronjob_to_scheduler(
        self,
        cronjob_id: str,
        identifier: str,
        params: BaseConfigSchema,
        cron: str,
        second: str | None = None,
    ) -> None:
        trigger = self._build_cron_trigger(cron, second)

        cronjob_registration = get_cron_registry().get_cronjob(identifier)
        if not cronjob_registration:
            raise ValueError(f"定时任务类型 '{identifier}' 未注册")

        cronjob_function = cronjob_registration.function

        try:
            self.scheduler.add_job(
                self._execute_cronjob_wrapper,
                trigger=trigger,
                args=[cronjob_id, identifier, params, cronjob_function],
                kwargs={"definition_token": definition_version(identifier, params.model_dump_json(), cron, second)},
                id=cronjob_id,
                replace_existing=True,
            )
        except Exception as exc:  # noqa: BLE001 - retain desired config and expose failed registration
            self._registration_errors[cronjob_id] = "调度器注册失败，请重新启用任务"
            log_safe_error(exc, "Cron job registration failed")
        else:
            self._registration_errors.pop(cronjob_id, None)

    def _build_cron_trigger(
        self,
        cron: str,
        second: str | None = None,
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
            day_of_week=normalize_crontab_weekday(cron_parts[4]),
        )

    async def _execute_cronjob_wrapper(
        self,
        cronjob_id: str,
        identifier: str,
        params: BaseConfigSchema,
        cronjob_function,
        *,
        definition_token: str | None = None,
    ) -> None:
        """Run ``cronjob_function`` with execution context, recording the outcome."""
        timestamp = int(datetime.now(UTC).timestamp() * 1000)
        random_suffix = secrets.token_urlsafe(4)
        execution_id = f"{timestamp}_{random_suffix}"

        context = ExecutionContext(
            cronjob_id=cronjob_id,
            identifier=identifier,
            execution_id=execution_id,
            params=params,
            started_at=datetime.now(UTC),
            status=ExecutionStatus.RUNNING,
        )

        worker = asyncio.current_task()
        if worker is not None:
            self._executions.add(worker)
        started_recorded = False
        operation = None
        try:
            async with get_async_session() as session:
                await crud.create_execution_record(session, context.to_execution_record())
            started_recorded = True
            async with get_async_session() as session:
                job = await crud.get_cronjob(session, cronjob_id)
                if job is None:
                    context.skip("定时任务配置已删除，跳过执行")
                    return
                problem = await managed_binding_problem(session, job)
                if problem:
                    context.skip(problem)
                    return
                if job.status != CronJobStatus.ACTIVE:
                    context.skip("定时任务已暂停或取消，跳过执行")
                    return
                if definition_token is not None and definition_token != definition_version(job.identifier, job.params_json, job.cron, job.second):
                    context.skip("定时任务配置已变更，跳过旧调度")
                    return
                context.managed_server_generation = job.managed_server_generation
            server_id = getattr(params, "server_id", None)
            server_ids = [server_id] if server_id else []
            claims = None
            if identifier == "backup" and not server_ids:
                from ..minecraft import get_docker_mc_manager

                server_ids = [instance.get_name() for instance in await get_docker_mc_manager().get_all_instances()]
                claims = [ResourceClaim(ResourceKind.FILES)]
            async with operation_scope(
                f"cron_{identifier}", server_ids, origin="cron", legacy_id=execution_id, claims=claims,
            ) as operation:
                await record_phase("executing_schedule")
                await cronjob_function(context)
                if operation is not None and context.status == ExecutionStatus.SKIPPED:
                    operation.outcome = OperationState.SKIPPED
            if context.status == ExecutionStatus.RUNNING:
                context.status = ExecutionStatus.COMPLETED
        except asyncio.CancelledError:
            context.status = ExecutionStatus.CANCELLED
            context.log("定时任务执行已取消")
            raise
        except Exception as e:  # noqa: BLE001 - persist a safe failure for every scheduled invocation
            log_safe_error(e, "Cron job failed")
            context.status = ExecutionStatus.FAILED
            context.log(f"定时任务执行失败: {public_error_message(e)}")
        finally:
            context.ended_at = datetime.now(UTC)
            if context.ended_at and context.started_at:
                context.duration_ms = int(
                    (context.ended_at - context.started_at).total_seconds() * 1000
                )

            async def persist_result() -> None:
                if not started_recorded:
                    return
                if operation is not None:
                    recorded = await operation.journal.get(operation.operation_id)
                    if recorded is not None and recorded.state in TERMINAL_STATES:
                        context.status = {
                            OperationState.SUCCEEDED: ExecutionStatus.COMPLETED,
                            OperationState.CANCELLED: ExecutionStatus.CANCELLED,
                            OperationState.SKIPPED: ExecutionStatus.SKIPPED,
                        }.get(recorded.state, ExecutionStatus.FAILED)
                        if not recorded.writers_stopped or not recorded.ownership_known or recorded.processes:
                            context.status = ExecutionStatus.FAILED
                        if recorded.state is OperationState.INTERRUPTED or not recorded.writers_stopped:
                            context.log("操作已中断，所属写入需要恢复验证，请查看操作历史")
                async with get_async_session() as session:
                    await crud.finish_execution_record(session, context.to_execution_record())

            try:
                await finalize(persist_result())
            finally:
                if worker is not None:
                    self._executions.discard(worker)

    async def _recover_cronjobs_from_database(self) -> None:
        logger = get_logger()
        async with get_async_session() as session:
            active_cronjobs = await crud.get_cronjobs_by_status(
                session, CronJobStatus.ACTIVE
            )

            for cronjob_row in active_cronjobs:
                problem = await managed_binding_problem(session, cronjob_row)
                if problem:
                    logger.warning("Cron job %s is not scheduled: %s", cronjob_row.cronjob_id, problem)
                    continue
                schema_cls = get_cron_registry().get_schema_class(cronjob_row.identifier)
                if not schema_cls:
                    continue

                try:
                    params = schema_cls.model_validate_json(cronjob_row.params_json)
                except (ValueError, TypeError):
                    self._registration_errors[cronjob_row.cronjob_id] = "定时任务配置无效，请修改后重新启用"
                    continue

                try:
                    await self._submit_cronjob_to_scheduler(
                        cronjob_row.cronjob_id, cronjob_row.identifier, params,
                        cronjob_row.cron, cronjob_row.second,
                    )
                except (ValueError, TypeError):
                    self._registration_errors[cronjob_row.cronjob_id] = "定时任务配置无效，请修改后重新启用"

    async def _ensure_system_cronjobs(self) -> None:
        """Create and repair code-defined system cron jobs."""
        logger = get_logger()
        for identifier, registration in get_cron_registry().get_all_cronjobs().items():
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
                            exc_info=True,
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
                            exc_info=True,
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
