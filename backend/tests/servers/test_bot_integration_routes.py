import asyncio
import json
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import api_app
from app.minecraft import MCServerStatus
from app.routers.servers.misc import get_servers_overview
from app.runtime_resources import current_runtime
from tests.support.runtime import patch_runtime_resource


def auth_headers() -> dict[str, str]:
    return {"Authorization": "Bearer test-master-token"}


@pytest.fixture
def client():
    with patch.object(current_runtime().settings, 'master_token', "test-master-token"):
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

    with patch_runtime_resource('docker_mc_manager') as manager:
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

    with patch_runtime_resource('docker_mc_manager') as manager:
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

    with patch_runtime_resource('docker_mc_manager') as manager:
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
        patch_runtime_resource('docker_mc_manager') as manager,
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

    with patch_runtime_resource('docker_mc_manager') as manager:
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








@pytest.mark.asyncio
async def test_overview_skips_drift_and_hides_players_for_stopped_servers(
    database, isolated_runtime, monkeypatch, caplog,
):
    from datetime import UTC, datetime

    from app.auth.schemas import UserPublic
    from app.minecraft import MCInstance
    from app.players.models import Player, PlayerSession
    from app.servers.models import Server
    from tests.fixtures.test_utils import create_mc_server_compose_yaml

    now = datetime.now(UTC)
    async with database.session_factory() as session:
        running, stopped, drifted = [Server(server_id=name) for name in ("running", "stopped", "drifted")]
        notch = Player(uuid="069a79f444e94726a5befca90e38aaf5", current_name="Notch", created_at=now)
        ghost = Player(uuid="123e4567e89b42d3a456426614174000", current_name="Ghost", created_at=now)
        session.add_all([running, stopped, drifted, notch, ghost])
        await session.flush()
        session.add_all([
            PlayerSession(player_db_id=notch.player_db_id, server_db_id=running.id, joined_at=now),
            PlayerSession(player_db_id=ghost.player_db_id, server_db_id=stopped.id, joined_at=now),
        ])
        await session.commit()
    manager = isolated_runtime.docker_mc_manager
    for name in ("running", "stopped"):
        await manager.get_instance(name).create(create_mc_server_compose_yaml(name, 25565, 25575))

    async def docker_status(instance):
        return MCServerStatus.HEALTHY if instance.get_name() == "running" else MCServerStatus.CREATED

    monkeypatch.setattr(MCInstance, "get_status", docker_status)
    with caplog.at_level(logging.WARNING):
        async with database.session_factory() as session:
            result = await get_servers_overview(
                db=session, _=UserPublic(id=1, username="owner", created_at=now),
            )

    assert [server.id for server in result] == ["running", "stopped"]
    assert [player.name for player in result[0].online_players] == ["Notch"]
    assert result[1].online_players == []
    assert any("drifted" in record.message for record in caplog.records)
