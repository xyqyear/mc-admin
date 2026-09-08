"""Cron manager bound to a test-only registry, isolated from production jobs."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

import app.cron.manager as manager_module
from app.cron.manager import CronManager

from .test_cronjobs import test_cron_registry


class TestCronManager(CronManager):
    # Prevent pytest from collecting this class as a test class.
    __test__ = False

    def __init__(self):
        super().__init__()
        self._registry_patch = patch.object(
            manager_module, "cron_registry", test_cron_registry
        )

    async def initialize(self) -> None:
        if self._initialized:
            return
        self._registry_patch.start()
        try:
            await super().initialize()
        finally:
            if not self._initialized:
                await self.shutdown()

    async def shutdown(self) -> None:
        try:
            await super().shutdown()
        finally:
            self._registry_patch.stop()
            self._initialized = False


test_cron_manager = TestCronManager()


def test_manager_construction_does_not_replace_global_registry():
    original = manager_module.cron_registry
    manager = TestCronManager()

    assert manager_module.cron_registry is original
    assert not manager._initialized


async def test_initialization_failure_restores_global_registry(monkeypatch):
    original = manager_module.cron_registry
    manager = TestCronManager()

    async def initialize(instance):
        instance.scheduler.start()
        raise RuntimeError("startup failed")

    monkeypatch.setattr(CronManager, "initialize", initialize)

    with pytest.raises(RuntimeError, match="startup failed"):
        await manager.initialize()
    await asyncio.sleep(0)

    assert manager_module.cron_registry is original
    assert not manager.scheduler.running


async def test_shutdown_failure_restores_global_registry(monkeypatch):
    original = manager_module.cron_registry
    manager = TestCronManager()

    async def initialize(instance):
        instance._initialized = True

    monkeypatch.setattr(CronManager, "initialize", initialize)
    monkeypatch.setattr(
        CronManager, "shutdown", AsyncMock(side_effect=RuntimeError("shutdown failed"))
    )
    await manager.initialize()
    assert manager_module.cron_registry is test_cron_registry

    with pytest.raises(RuntimeError, match="shutdown failed"):
        await manager.shutdown()

    assert manager_module.cron_registry is original
    assert not manager._initialized
