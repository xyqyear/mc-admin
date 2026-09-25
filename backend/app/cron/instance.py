"""
Global cron manager instance.
"""

from ..runtime_resources import current_runtime
from .manager import CronManager


# Global cron manager instance
def get_cron_manager() -> CronManager:
    return current_runtime().resource('cron_manager')
