"""
Cron job management system for MC Admin.

This module provides a comprehensive cron job scheduling and management system
built on top of APScheduler, allowing for asynchronous cron job execution with
full lifecycle management, persistence, and monitoring.
"""

from .instance import cron_manager
from .manager import CronManager
from .registry import CronRegistry, cron_registry
from .restart_scheduler import RestartScheduler
from .types import (
    AsyncCronJobFunction,
    CronJobConfig,
    CronJobExecutionRecord,
    CronJobRegistration,
    ExecutionContext,
)

__all__ = [
    "CronRegistry",
    "cron_registry",
    "CronManager",
    "cron_manager",
    "RestartScheduler",
    "ExecutionContext",
    "CronJobConfig",
    "CronJobExecutionRecord",
    "CronJobRegistration",
    "AsyncCronJobFunction",
]
