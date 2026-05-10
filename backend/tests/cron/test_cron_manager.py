"""Cron manager bound to a test-only registry, isolated from production jobs."""

from app.cron.manager import CronManager

from .test_cronjobs import test_cron_registry


class TestCronManager(CronManager):
    # Prevent pytest from collecting this class as a test class.
    __test__ = False

    def __init__(self):
        super().__init__()
        import app.cron.manager

        self._original_registry = app.cron.manager.cron_registry
        app.cron.manager.cron_registry = test_cron_registry

    def __del__(self):
        import app.cron.manager

        app.cron.manager.cron_registry = self._original_registry


test_cron_manager = TestCronManager()
