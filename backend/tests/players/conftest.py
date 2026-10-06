from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.players import get_player_service
from app.players.skin_fetcher import SkinFetcher
from app.runtime_resources import current_runtime
from tests.players.helpers import cleanup_test_db, create_test_db


@pytest.fixture
async def test_database(isolated_runtime) -> AsyncGenerator[Any]:
    session, engine, path = await create_test_db()
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    @asynccontextmanager
    async def get_session():
        async with factory() as owned_session:
            yield owned_session

    try:
        yield get_session
    finally:
        await cleanup_test_db(session, engine, path)


@pytest.fixture
async def player_system(test_database, mock_skin_fetcher, mock_mojang_api) -> AsyncGenerator[dict[str, Any]]:
    with (
        patch.object(get_player_service(), "session_factory", test_database),
        patch("app.players.mojang_api.fetch_player_uuid_from_mojang", mock_mojang_api),
        patch.object(SkinFetcher, "fetch_player_skin", mock_skin_fetcher),
    ):
        try:
            yield {"db": test_database}
        finally:
            await current_runtime().close()
