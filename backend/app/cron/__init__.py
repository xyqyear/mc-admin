"""
Cron job management system for MC Admin.

This module provides a comprehensive cron job scheduling and management system
built on top of APScheduler, allowing for asynchronous cron job execution with
full lifecycle management, persistence, and monitoring.
"""

from .instance import get_cron_manager
from .manager import CronManager
from .registry import CronRegistry, get_cron_registry
from .restart_scheduler import RestartScheduler, get_restart_scheduler
from .types import (
    AsyncCronJobFunction,
    CronJobConfig,
    CronJobExecutionRecord,
    CronJobRegistration,
    ExecutionContext,
)

__all__ = [
    "AsyncCronJobFunction",
    "CronJobConfig",
    "CronJobExecutionRecord",
    "CronJobRegistration",
    "CronManager",
    "CronRegistry",
    "ExecutionContext",
    "RestartScheduler",
    'get_cron_manager',
    'get_cron_registry',
    'get_restart_scheduler',
]
