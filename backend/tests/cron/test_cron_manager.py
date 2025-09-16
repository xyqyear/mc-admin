"""
Test-specific cron manager for isolated testing.

This module provides a cron manager that uses a test-specific registry,
ensuring that test cron jobs don't interfere with production cron job registration.
"""

from app.cron.manager import CronManager

from .test_cronjobs import test_cron_registry


class TestCronManager(CronManager):
    """
    Cron manager that uses test-specific registry.

    This ensures test cron jobs are isolated from production cron jobs.
    The approach here is to use the original CronManager code directly,
    but replace the cron_registry module import at the class level.
    """

    # Prevent pytest from collecting this class as a test class
    __test__ = False

    def __init__(self):
        super().__init__()
        # Replace the module-level cron_registry with our test registry
        # by monkey-patching the imported reference
        import app.cron.manager

        self._original_registry = app.cron.manager.cron_registry
        app.cron.manager.cron_registry = test_cron_registry

    def __del__(self):
        """Restore original registry when manager is destroyed."""
        import app.cron.manager

        app.cron.manager.cron_registry = self._original_registry


# Create a test-specific cron manager instance
test_cron_manager = TestCronManager()
