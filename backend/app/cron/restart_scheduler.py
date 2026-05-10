"""Restart-task scheduler that avoids existing backup-task minutes."""

from datetime import time
from typing import Optional, Set, Tuple

from ..models import CronJobStatus
from .instance import cron_manager
from .manager import CronManager


class RestartScheduler:
    """Pick restart times that don't collide with active backup or other restart cron jobs."""

    def __init__(
        self, cron_manager: CronManager, restart_start_time: time = time(6, 0)
    ):
        self.cron_manager = cron_manager
        self.restart_start_time = restart_start_time

    async def get_backup_minutes(self) -> Set[int]:
        backup_jobs = await self.cron_manager.get_all_cronjobs(
            identifier="backup", status=[CronJobStatus.ACTIVE, CronJobStatus.PAUSED]
        )

        backup_minutes = set()

        for job in backup_jobs:
            cron_parts = job.cron.strip().split()
            if len(cron_parts) >= 1:
                minute_part = cron_parts[0]

                minutes = self._parse_cron_minute_field(minute_part)
                backup_minutes.update(minutes)

        return backup_minutes

    async def get_restart_time_slots(
        self, exclude_server_id: Optional[str] = None
    ) -> Set[Tuple[int, int]]:
        """``(hour, minute)`` pairs already taken by active restart_server jobs."""
        restart_jobs = await self.cron_manager.get_all_cronjobs(
            identifier="restart_server",
            status=[CronJobStatus.ACTIVE, CronJobStatus.PAUSED],
        )

        restart_time_slots = set()

        for job in restart_jobs:
            # Don't conflict with the very job we're rescheduling.
            if exclude_server_id:
                schedule_name = f"restart-{exclude_server_id}"
                if job.name == schedule_name:
                    continue

            cron_parts = job.cron.strip().split()
            if len(cron_parts) >= 2:
                minute_part = cron_parts[0]
                hour_part = cron_parts[1]

                minutes = self._parse_cron_minute_field(minute_part)
                hours = self._parse_cron_hour_field(hour_part)

                for hour in hours:
                    for minute in minutes:
                        restart_time_slots.add((hour, minute))

        return restart_time_slots

    def _parse_cron_field(self, field_value: str, max_value: int) -> Set[int]:
        """Expand a cron field to its concrete value set; supports `*`, lists, ranges, steps."""
        values = set()

        if field_value == "*":
            return set(range(max_value))

        for part in field_value.split(","):
            part = part.strip()

            if "/" in part:
                base_part, step_str = part.split("/", 1)
                step = int(step_str)

                if base_part == "*":
                    values.update(range(0, max_value, step))
                elif "-" in base_part:
                    start_str, end_str = base_part.split("-", 1)
                    start, end = int(start_str), int(end_str)
                    values.update(range(start, end + 1, step))
                else:
                    start = int(base_part)
                    values.update(range(start, max_value, step))

            elif "-" in part:
                start_str, end_str = part.split("-", 1)
                start, end = int(start_str), int(end_str)
                values.update(range(start, end + 1))

            else:
                values.add(int(part))

        return values

    def _parse_cron_minute_field(self, minute_field: str) -> Set[int]:
        return self._parse_cron_field(minute_field, 60)

    def _parse_cron_hour_field(self, hour_field: str) -> Set[int]:
        return self._parse_cron_field(hour_field, 24)

    async def find_next_available_restart_time(
        self, exclude_server_id: Optional[str] = None
    ) -> Tuple[int, int]:
        """First 5-minute slot from ``restart_start_time`` not used by backups or other restarts."""
        backup_minutes = await self.get_backup_minutes()
        restart_time_slots = await self.get_restart_time_slots(exclude_server_id)

        current_hour = self.restart_start_time.hour
        current_minute = self.restart_start_time.minute

        current_minute = (current_minute // 5) * 5

        for _ in range(24 * 60 // 5):
            if current_minute not in backup_minutes:
                if (current_hour, current_minute) not in restart_time_slots:
                    return (current_hour, current_minute)

            current_minute += 5
            if current_minute >= 60:
                current_minute = 0
                current_hour += 1
                if current_hour >= 24:
                    current_hour = 0

        return (self.restart_start_time.hour, self.restart_start_time.minute)

    async def generate_restart_cron(
        self,
        day_pattern: str = "*",
        month_pattern: str = "*",
        weekday_pattern: str = "*",
        exclude_server_id: Optional[str] = None,
    ) -> str:
        hour, minute = await self.find_next_available_restart_time(exclude_server_id)

        return f"{minute} {hour} {day_pattern} {month_pattern} {weekday_pattern}"

    async def check_time_conflict(
        self, hour: int, minute: int, exclude_server_id: Optional[str] = None
    ) -> bool:
        """Whether ``(hour, minute)`` collides with any active backup or other restart slot."""
        backup_minutes = await self.get_backup_minutes()
        restart_time_slots = await self.get_restart_time_slots(exclude_server_id)

        if minute in backup_minutes:
            return True

        if (hour, minute) in restart_time_slots:
            return True

        return False


restart_scheduler = RestartScheduler(cron_manager)
