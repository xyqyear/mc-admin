"""Unit tests for /servers/ (the overview) under the DB-driven discovery model.

Covers the drifted-row path: an ACTIVE row whose compose can't be read must
not surface in the response but MUST produce a warning log so operators can
correlate with the sync endpoint.
"""

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.minecraft import MCServerInfo
from app.minecraft.compose import ServerType
from app.routers.servers.misc import get_servers


def _row(server_id: str) -> MagicMock:
    row = MagicMock()
    row.server_id = server_id
    return row


def _info(name: str, *, game_port: int = 25565, rcon_port: int = 25575) -> MCServerInfo:
    return MCServerInfo(
        name=name,
        path=f"/servers/{name}",
        java_version=17,
        max_memory_bytes=2048 * 1024 * 1024,
        server_type=ServerType.VANILLA,
        game_version="1.20.1",
        game_port=game_port,
        rcon_port=rcon_port,
    )


@pytest.mark.asyncio
async def test_get_servers_filters_drifted_row_and_logs(caplog):
    """ACTIVE row whose compose read raises is filtered with a warning;
    the surviving row still appears in the response."""
    good_instance = MagicMock()
    good_instance.get_name = MagicMock(return_value="good")
    good_instance.get_server_info = AsyncMock(return_value=_info("good"))

    bad_instance = MagicMock()
    bad_instance.get_name = MagicMock(return_value="drifted")
    bad_instance.get_server_info = AsyncMock(
        side_effect=FileNotFoundError("compose.yml missing")
    )

    fake_manager = MagicMock()
    fake_manager.get_instance = MagicMock(
        side_effect={"good": good_instance, "drifted": bad_instance}.__getitem__
    )

    rows = [_row("good"), _row("drifted")]

    with (
        patch("app.routers.servers.misc.docker_mc_manager", fake_manager),
        patch(
            "app.routers.servers.misc.get_active_servers",
            AsyncMock(return_value=rows),
        ),
        caplog.at_level(logging.WARNING),
    ):
        result = await get_servers(db=AsyncMock(), _=MagicMock())

    assert [s.id for s in result] == ["good"]
    assert any(
        "drifted" in record.message and "cannot read compose" in record.message
        for record in caplog.records
    )


@pytest.mark.asyncio
async def test_get_servers_empty_when_no_active_rows():
    """Short-circuit on empty DB — no filesystem call, no warnings."""
    fake_manager = MagicMock()
    fake_manager.get_instance = MagicMock(side_effect=AssertionError("should not be called"))

    with (
        patch("app.routers.servers.misc.docker_mc_manager", fake_manager),
        patch(
            "app.routers.servers.misc.get_active_servers",
            AsyncMock(return_value=[]),
        ),
    ):
        result = await get_servers(db=AsyncMock(), _=MagicMock())

    assert result == []
