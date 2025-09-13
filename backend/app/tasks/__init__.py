"""Simplified task system module for MC Admin.

This module provides a lightweight runtime task management system,
supporting immediate task submission and scheduled task execution.
"""

from .manager import TaskManager
from .models import AsyncFunc, TaskInfo, TaskStatus, TaskType

__all__ = [
    "TaskManager",
    "TaskInfo", 
    "TaskStatus",
    "TaskType",
    "AsyncFunc",
]