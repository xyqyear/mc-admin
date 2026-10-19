from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from app.players.skin_fetcher import SkinFetcher
from app.runtime_resources import current_runtime


@pytest.fixture
async def test_database(db_session_factory):
    return db_session_factory


@pytest.fixture
async def player_system(test_database, mock_skin_fetcher, mock_mojang_api) -> AsyncGenerator[dict[str, Any]]:
    with (
        patch("app.players.mojang_api.fetch_player_uuid_from_mojang", mock_mojang_api),
        patch.object(SkinFetcher, "fetch_player_skin", mock_skin_fetcher),
    ):
        try:
            yield {"db": test_database}
        finally:
            await current_runtime().close()


@pytest.fixture(autouse=True)
async def external_skin_client(isolated_runtime, monkeypatch):
    monkeypatch.setattr(SkinFetcher, "fetch_player_skin", AsyncMock(return_value=None))
    try:
        yield
    finally:
        await isolated_runtime.close()
