"""
Restart Task Scheduler - Utility for scheduling server restart tasks without conflicts.

This module provides utilities to schedule server restart tasks while avoiding
conflicts with existing backup tasks by analyzing their cron schedules.
"""

from datetime import time
from typing import Optional, Set, Tuple

from ..models import CronJobStatus
from .manager import CronManager


class RestartScheduler:
    """
    Utility class for scheduling server restart tasks that avoid backup conflicts.

    This class analyzes existing backup task schedules and finds suitable
    restart times that don't conflict with backup operations.
    """

    def __init__(
        self, cron_manager: CronManager, restart_start_time: time = time(6, 0)
    ):
        """
        Initialize the restart scheduler.

        Args:
            cron_manager: CronManager instance for querying existing jobs
            restart_start_time: Starting time for restart scheduling (default: 06:00)
        """
        self.cron_manager = cron_manager
        self.restart_start_time = restart_start_time

    async def get_backup_minutes(self) -> Set[int]:
        """
        Get all minutes used by backup tasks from their cron expressions.

        Returns:
            Set of minutes (0-59) used by backup tasks
        """
        # Get all active backup tasks
        backup_jobs = await self.cron_manager.get_all_cronjobs(
            identifier="backup", status=[CronJobStatus.ACTIVE, CronJobStatus.PAUSED]
        )

        backup_minutes = set()

        for job in backup_jobs:
            cron_parts = job.cron.strip().split()
            if len(cron_parts) >= 1:
                minute_part = cron_parts[0]

                # Parse minute expressions (supports single, list, range, step values)
                minutes = self._parse_cron_minute_field(minute_part)
                backup_minutes.update(minutes)

        return backup_minutes

    async def get_restart_time_slots(
        self, exclude_server_id: Optional[str] = None
    ) -> Set[Tuple[int, int]]:
        """
        Get all hour:minute combinations used by restart_server tasks.

        Args:
            exclude_server_id: Optional server ID to exclude from consideration
                              (useful when creating/updating a schedule for that server)

        Returns:
            Set of (hour, minute) tuples used by restart_server tasks
        """
        # Get all active restart_server tasks
        restart_jobs = await self.cron_manager.get_all_cronjobs(
            identifier="restart_server",
            status=[CronJobStatus.ACTIVE, CronJobStatus.PAUSED],
        )

        restart_time_slots = set()

        for job in restart_jobs:
            # Skip if this is the job for the server we're trying to schedule
            if exclude_server_id:
                schedule_name = f"restart-{exclude_server_id}"
                if job.name == schedule_name:
                    continue

            cron_parts = job.cron.strip().split()
            if len(cron_parts) >= 2:
                minute_part = cron_parts[0]
                hour_part = cron_parts[1]

                # Parse minute and hour expressions
                minutes = self._parse_cron_minute_field(minute_part)
                hours = self._parse_cron_hour_field(hour_part)

                # Add all combinations of hour:minute
                for hour in hours:
                    for minute in minutes:
                        restart_time_slots.add((hour, minute))

        return restart_time_slots

    def _parse_cron_field(self, field_value: str, max_value: int) -> Set[int]:
        """
        Parse a cron field and return all possible values.

        Supports:
        - Single values: "30"
        - Lists: "0,15,30"
        - Ranges: "0-15"
        - Step values: "*/5", "0-30/10"
        - Wildcards: "*"

        Args:
            field_value: Cron field string
            max_value: Maximum value for this field (60 for minutes, 24 for hours)

        Returns:
            Set of integer values within the field's range
        """
        values = set()

        # Handle wildcard
        if field_value == "*":
            return set(range(max_value))

        # Split by comma for multiple values
        for part in field_value.split(","):
            part = part.strip()

            # Handle step values (e.g., "*/5", "0-30/5")
            if "/" in part:
                base_part, step_str = part.split("/", 1)
                step = int(step_str)

                if base_part == "*":
                    # */step pattern
                    values.update(range(0, max_value, step))
                elif "-" in base_part:
                    # range/step pattern (e.g., "0-30/5")
                    start_str, end_str = base_part.split("-", 1)
                    start, end = int(start_str), int(end_str)
                    values.update(range(start, end + 1, step))
                else:
                    # single value with step (treat as start point)
                    start = int(base_part)
                    values.update(range(start, max_value, step))

            # Handle ranges (e.g., "0-15")
            elif "-" in part:
                start_str, end_str = part.split("-", 1)
                start, end = int(start_str), int(end_str)
                values.update(range(start, end + 1))

            # Handle single values
            else:
                values.add(int(part))

        return values

    def _parse_cron_minute_field(self, minute_field: str) -> Set[int]:
        """
        Parse a cron minute field and return all possible minute values.

        Supports:
        - Single values: "30"
        - Lists: "0,15,30"
        - Ranges: "0-15"
        - Step values: "*/5", "0-30/10"
        - Wildcards: "*"

        Args:
            minute_field: Cron minute field string

        Returns:
            Set of minute values (0-59)
        """
        return self._parse_cron_field(minute_field, 60)

    def _parse_cron_hour_field(self, hour_field: str) -> Set[int]:
        """
        Parse a cron hour field and return all possible hour values.

        Supports the same patterns as minute field but for hours (0-23).

        Args:
            hour_field: Cron hour field string

        Returns:
            Set of hour values (0-23)
        """
        return self._parse_cron_field(hour_field, 24)

    async def find_next_available_restart_time(
        self, exclude_server_id: Optional[str] = None
    ) -> Tuple[int, int]:
        """
        Find the next available restart time that doesn't conflict with backups or other restart tasks.

        Starting from restart_start_time, finds the first time slot where:
        1. Minutes are divisible by 5 (0, 5, 10, 15, ...)
        2. Minutes don't conflict with any backup task minutes
        3. Hour:minute combination doesn't conflict with other restart tasks

        Args:
            exclude_server_id: Optional server ID to exclude when checking restart conflicts

        Returns:
            Tuple of (hour, minute) for the next available restart time
        """
        backup_minutes = await self.get_backup_minutes()
        restart_time_slots = await self.get_restart_time_slots(exclude_server_id)

        # Start from the configured restart start time
        current_hour = self.restart_start_time.hour
        current_minute = self.restart_start_time.minute

        # Round down to current 5-minute interval first
        current_minute = (current_minute // 5) * 5

        # Search for available slot
        for _ in range(24 * 60 // 5):  # Max iterations to avoid infinite loop
            # Check if current minute conflicts with backup minutes
            if current_minute not in backup_minutes:
                # Check if current hour:minute conflicts with other restart tasks
                if (current_hour, current_minute) not in restart_time_slots:
                    return (current_hour, current_minute)

            # Move to next 5-minute interval
            current_minute += 5
            if current_minute >= 60:
                current_minute = 0
                current_hour += 1
                if current_hour >= 24:
                    current_hour = 0

        # Fallback: return original start time if no slot found
        return (self.restart_start_time.hour, self.restart_start_time.minute)

    async def generate_restart_cron(
        self,
        day_pattern: str = "*",
        month_pattern: str = "*",
        weekday_pattern: str = "*",
        exclude_server_id: Optional[str] = None,
    ) -> str:
        """
        Generate a cron expression for server restart that avoids backup and restart conflicts.

        Args:
            day_pattern: Day of month pattern (default: "*" for every day)
            month_pattern: Month pattern (default: "*" for every month)
            weekday_pattern: Day of week pattern (default: "*" for every day)
            exclude_server_id: Optional server ID to exclude when checking restart conflicts

        Returns:
            Complete cron expression string (5 fields: minute hour day month weekday)
        """
        hour, minute = await self.find_next_available_restart_time(exclude_server_id)

        return f"{minute} {hour} {day_pattern} {month_pattern} {weekday_pattern}"

    async def check_time_conflict(
        self, hour: int, minute: int, exclude_server_id: Optional[str] = None
    ) -> bool:
        """
        Check if a specific time conflicts with existing backup tasks or other restart tasks.

        Args:
            hour: Hour to check (0-23)
            minute: Minute to check (0-59)
            exclude_server_id: Optional server ID to exclude when checking restart conflicts

        Returns:
            True if there's a conflict, False otherwise
        """
        backup_minutes = await self.get_backup_minutes()
        restart_time_slots = await self.get_restart_time_slots(exclude_server_id)

        # Check backup minute conflicts
        if minute in backup_minutes:
            return True

        # Check restart time slot conflicts
        if (hour, minute) in restart_time_slots:
            return True

        return False
