from tests.cron.test_cronjobs import assert_next_calendar_day

"""Cron expression validation and execution timing tests."""

from datetime import datetime

import pytest
from sqlalchemy import select

from app.cron.models import CronJob
from app.db.database import get_async_session

from .test_cronjobs import SampleCronJobParams

pytestmark = pytest.mark.usefixtures("setup_test_db")


class TestCronScheduling:

    async def test_cron_validation_with_different_expressions(self, fresh_cron_manager):
        cron_manager = fresh_cron_manager
        params = SampleCronJobParams(message="Validation test")

        test_cases = [
            ("0 0 * * *", None, "Daily at midnight"),
            ("0 */2 * * *", None, "Every 2 hours"),
            ("30 9 * * 1-5", None, "9:30 AM on weekdays"),
            ("0 0 1 * *", None, "First day of every month"),
            ("* * * * *", "*", "Every second"),
            ("*/5 * * * *", None, "Every 5 minutes"),
        ]

        reference = datetime(2026, 1, 4, 8, 7, 12, tzinfo=cron_manager.scheduler.timezone)
        expected_dates = [
            (2026, 1, 5, 0, 0, 0), (2026, 1, 4, 10, 0, 0),
            (2026, 1, 5, 9, 30, 0), (2026, 2, 1, 0, 0, 0),
            (2026, 1, 4, 8, 7, 12), (2026, 1, 4, 8, 10, 0),
        ]
        created_cronjobs = []

        for (cron_expr, second, description), expected in zip(test_cases, expected_dates, strict=True):
            cronjob_id = await cron_manager.create_cronjob(
                identifier="test_cronjob",
                params=params,
                cron=cron_expr,
                second=second,
                name=f"Cron Test: {description}",
            )

            created_cronjobs.append(cronjob_id)

            scheduled_job = cron_manager.scheduler.get_job(cronjob_id)
            assert scheduled_job is not None, (
                f"Cron expression '{cron_expr}' should be valid"
            )

            assert scheduled_job.trigger.get_next_fire_time(None, reference) == datetime(
                *expected, tzinfo=cron_manager.scheduler.timezone,
            )

        scheduled_job_ids = [job.id for job in cron_manager.scheduler.get_jobs()]
        for cronjob_id in created_cronjobs:
            assert cronjob_id in scheduled_job_ids, (
                f"CronJob {cronjob_id} should be scheduled"
            )

    async def test_invalid_cron_expressions(self, fresh_cron_manager):
        cron_manager = fresh_cron_manager
        params = SampleCronJobParams(message="Invalid cron test")

        invalid_cron_expressions = [
            "invalid",
            "60 * * * *",  # minute > 59
            "* 25 * * *",  # hour > 23
            "* * 32 * *",  # day > 31
            "* * * 13 *",  # month > 12
            "* * * * 8",  # dow > 7
        ]

        for invalid_cron in invalid_cron_expressions:
            with pytest.raises(ValueError) as error:
                await cron_manager.create_cronjob(
                    identifier="test_cronjob",
                    params=params,
                    cron=invalid_cron,
                    name=f"Invalid Cron Test: {invalid_cron}",
                )

            error_msg = str(error.value).lower()
            assert any(
                keyword in error_msg
                for keyword in ["cron", "invalid", "error", "value", "expression"]
            ), f"Expected cron-related error for '{invalid_cron}', got: {error.value}"

    async def test_weekday_expression_is_preserved_and_update_is_atomic(
        self, fresh_cron_manager
    ):
        cron_manager = fresh_cron_manager
        params = SampleCronJobParams(message="Weekday lifecycle test")

        cronjob_id = await cron_manager.create_cronjob(
            identifier="test_cronjob",
            params=params,
            cron="0 1 * * 1",
        )

        async with get_async_session() as session:
            result = await session.execute(
                select(CronJob).where(CronJob.cronjob_id == cronjob_id)
            )
            row = result.scalar_one()
            assert row.cron == "0 1 * * 1"

        scheduled_job = cron_manager.scheduler.get_job(cronjob_id)
        assert scheduled_job is not None
        assert_next_calendar_day(scheduled_job, 0)

        with pytest.raises(ValueError, match="星期字段"):
            await cron_manager.update_cronjob(
                cronjob_id=cronjob_id,
                identifier="test_cronjob",
                params=params,
                cron="0 1 * * 8",
            )

        async with get_async_session() as session:
            result = await session.execute(
                select(CronJob).where(CronJob.cronjob_id == cronjob_id)
            )
            row = result.scalar_one()
            assert row.cron == "0 1 * * 1"

        scheduled_job = cron_manager.scheduler.get_job(cronjob_id)
        assert scheduled_job is not None
        assert_next_calendar_day(scheduled_job, 0)

        await cron_manager.pause_cronjob(cronjob_id)
        await cron_manager.resume_cronjob(cronjob_id)

        scheduled_job = cron_manager.scheduler.get_job(cronjob_id)
        assert scheduled_job is not None
        assert_next_calendar_day(scheduled_job, 0)
