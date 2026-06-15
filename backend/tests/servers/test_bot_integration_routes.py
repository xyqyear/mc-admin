import asyncio
import json
import logging
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import api_app
from app.minecraft import MCServerInfo, MCServerStatus
from app.minecraft.compose import ServerType
from app.players.crud.query.session_query import OnlinePlayerLite
from app.routers.servers.misc import get_servers_overview


def auth_headers() -> dict[str, str]:
    return {"Authorization": "Bearer test-master-token"}


@pytest.fixture
def client():
    with patch("app.auth.session.settings.master_token", "test-master-token"):
        yield TestClient(api_app, raise_server_exceptions=False)


def mock_instance(
    *,
    exists: bool = True,
    healthy: bool = True,
    output: str = "ok",
):
    instance = MagicMock()
    instance.exists = AsyncMock(return_value=exists)
    instance.healthy = AsyncMock(return_value=healthy)
    instance.send_command_rcon = AsyncMock(return_value=output)
    return instance


def test_rcon_returns_command_output(client):
    instance = mock_instance(output="Added Notch to the whitelist")

    with patch("app.routers.servers.rcon.docker_mc_manager") as manager:
        manager.get_instance.return_value = instance

        response = client.post(
            "/servers/vanilla/rcon",
            json={"command": "whitelist add Notch"},
            headers=auth_headers(),
        )

    assert response.status_code == 200
    assert response.json() == {"output": "Added Notch to the whitelist"}
    instance.send_command_rcon.assert_awaited_once_with("whitelist add Notch")


def test_rcon_404_when_server_missing(client):
    instance = mock_instance(exists=False)

    with patch("app.routers.servers.rcon.docker_mc_manager") as manager:
        manager.get_instance.return_value = instance

        response = client.post(
            "/servers/missing/rcon",
            json={"command": "list"},
            headers=auth_headers(),
        )

    assert response.status_code == 404
    instance.healthy.assert_not_called()


def test_rcon_409_when_server_not_healthy(client):
    instance = mock_instance(healthy=False)

    with patch("app.routers.servers.rcon.docker_mc_manager") as manager:
        manager.get_instance.return_value = instance

        response = client.post(
            "/servers/vanilla/rcon",
            json={"command": "list"},
            headers=auth_headers(),
        )

    assert response.status_code == 409
    assert "未在健康状态" in response.json()["detail"]
    instance.send_command_rcon.assert_not_called()


def test_rcon_504_when_command_times_out(client):
    async def slow_command(_command: str) -> str:
        await asyncio.sleep(0.05)
        return "late"

    instance = mock_instance()
    instance.send_command_rcon = AsyncMock(side_effect=slow_command)

    with (
        patch("app.routers.servers.rcon.docker_mc_manager") as manager,
        patch("app.routers.servers.rcon.RCON_COMMAND_TIMEOUT", 0.001),
    ):
        manager.get_instance.return_value = instance

        response = client.post(
            "/servers/vanilla/rcon",
            json={"command": "list"},
            headers=auth_headers(),
        )

    assert response.status_code == 504


def test_message_sends_tellraw_json_per_non_empty_line(client):
    instance = mock_instance(output="")
    message = 'quote " slash \\\n你好\n\nsecond'

    with patch("app.routers.servers.rcon.docker_mc_manager") as manager:
        manager.get_instance.return_value = instance

        response = client.post(
            "/servers/vanilla/message",
            json={
                "message": message,
                "target_player": "Notch",
                "color": "aqua",
            },
            headers=auth_headers(),
        )

    assert response.status_code == 204
    commands = [call.args[0] for call in instance.send_command_rcon.await_args_list]
    assert len(commands) == 3

    payloads = []
    for command in commands:
        assert command.startswith("tellraw Notch ")
        payloads.append(json.loads(command.removeprefix("tellraw Notch ")))

    assert payloads == [
        {"text": 'quote " slash \\', "color": "aqua"},
        {"text": "你好", "color": "aqua"},
        {"text": "second", "color": "aqua"},
    ]
    assert "你好" in commands[1]


def test_message_rejects_selector_target(client):
    response = client.post(
        "/servers/vanilla/message",
        json={
            "message": "boom",
            "target_player": "@e[type=creeper]",
            "color": "yellow",
        },
        headers=auth_headers(),
    )

    assert response.status_code == 422
    assert "target_player" in response.json()["detail"]


def row(server_id: str) -> MagicMock:
    server_row = MagicMock()
    server_row.server_id = server_id
    return server_row


def server_info(server_id: str, game_port: int) -> MCServerInfo:
    return MCServerInfo(
        name=server_id,
        path=f"/servers/{server_id}",
        java_version=17,
        max_memory_bytes=2048,
        server_type=ServerType.VANILLA,
        game_version="1.20.1",
        game_port=game_port,
        rcon_port=25575,
    )


def overview_instance(
    server_id: str,
    *,
    status: MCServerStatus,
    game_port: int = 25565,
):
    instance = MagicMock()
    instance.get_name.return_value = server_id
    instance.get_server_info = AsyncMock(return_value=server_info(server_id, game_port))
    instance.get_status = AsyncMock(return_value=status)
    return instance


@pytest.mark.asyncio
async def test_overview_skips_drift_and_hides_players_for_stopped_servers(caplog):
    rows = [row("running"), row("stopped"), row("drifted")]
    running = overview_instance("running", status=MCServerStatus.HEALTHY)
    stopped = overview_instance("stopped", status=MCServerStatus.CREATED)
    drifted = overview_instance("drifted", status=MCServerStatus.HEALTHY)
    drifted.get_server_info = AsyncMock(side_effect=FileNotFoundError("missing"))

    manager = MagicMock()
    manager.get_instance.side_effect = {
        "running": running,
        "stopped": stopped,
        "drifted": drifted,
    }.__getitem__

    players = {
        "running": [
            OnlinePlayerLite(name="Notch", uuid="069a79f4", player_db_id=7)
        ],
        "stopped": [
            OnlinePlayerLite(name="Ghost", uuid="00000000", player_db_id=8)
        ],
    }

    with (
        patch("app.routers.servers.misc.docker_mc_manager", manager),
        patch("app.routers.servers.misc.get_active_servers", AsyncMock(return_value=rows)),
        patch(
            "app.routers.servers.misc.get_online_players_grouped_by_server",
            AsyncMock(return_value=players),
        ),
        caplog.at_level(logging.WARNING),
    ):
        result = await get_servers_overview(
            db=AsyncMock(),
            _=MagicMock(),
        )

    assert [server.id for server in result] == ["running", "stopped"]
    assert result[0].online_players == players["running"]
    assert result[1].online_players == []
    assert any("drifted" in record.message for record in caplog.records)
