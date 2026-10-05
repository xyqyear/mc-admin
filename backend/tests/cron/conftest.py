from collections.abc import AsyncGenerator
from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.metadata import Base
from tests.support.runtime import patch_runtime_resource

from .test_cron_manager import TestCronManager


@pytest.fixture
async def setup_test_db(isolated_runtime, tmp_path) -> AsyncGenerator[None]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'cron.sqlite3'}")
    sessions = async_sessionmaker(
        bind=engine, class_=AsyncSession, autocommit=False,
        autoflush=False, expire_on_commit=False,
    )
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        with (
            patch_runtime_resource("session_factory", sessions),
            patch_runtime_resource("database_engine", engine),
            patch("app.cron.manager.get_async_session", side_effect=sessions),
        ):
            yield
    finally:
        await engine.dispose()


@pytest.fixture
async def fresh_cron_manager(setup_test_db) -> AsyncGenerator[TestCronManager]:
    manager = TestCronManager()
    try:
        await manager.initialize()
        yield manager
    finally:
        await manager.shutdown()
