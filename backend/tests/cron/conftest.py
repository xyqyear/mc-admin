from collections.abc import AsyncGenerator
from contextlib import AsyncExitStack

import pytest

from tests.support.runtime import patch_runtime_resource

from .test_cron_manager import TestCronManager


@pytest.fixture
async def setup_test_db(database):
    return database


@pytest.fixture
async def fresh_cron_manager(setup_test_db) -> AsyncGenerator[TestCronManager]:
    manager = TestCronManager()
    with patch_runtime_resource("cron_manager", manager):
        try:
            await manager.initialize()
            yield manager
        finally:
            await manager.shutdown()


@pytest.fixture
def test_cron_registry(fresh_cron_manager):
    return fresh_cron_manager.registry


@pytest.fixture
async def manager_factory(setup_test_db):
    async with AsyncExitStack() as cleanup:
        def create():
            manager = TestCronManager()
            cleanup.push_async_callback(manager.shutdown)
            return manager

        yield create
