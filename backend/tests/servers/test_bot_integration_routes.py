import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import api_app
from app.minecraft.docker.commands import ServerMissing, ServerUnavailable
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
    error = ServerMissing("服务器不存在") if not exists else (ServerUnavailable("未在健康状态") if not healthy else None)
    instance.send_command_rcon = AsyncMock(return_value=output, side_effect=error)
    instance.get_command_container = AsyncMock(side_effect=error)
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
    instance.send_command_rcon.assert_awaited_once_with("list")


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


def test_message_failure_does_not_repeat_completed_lines(client):
    instance = mock_instance()
    instance.send_command_rcon.side_effect = ["ok", TimeoutError(), "unexpected"]
    with patch_runtime_resource('docker_mc_manager') as manager:
        manager.get_instance.return_value = instance
        response = client.post("/servers/vanilla/message", json={"message": "one\ntwo\nthree"}, headers=auth_headers())
    assert response.status_code == 504
    commands = [call.args[0] for call in instance.send_command_rcon.await_args_list]
    assert len(commands) == 2
    assert json.loads(commands[0].removeprefix("tellraw @a "))["text"] == "one"
    assert json.loads(commands[1].removeprefix("tellraw @a "))["text"] == "two"


def test_rcon_failure_hides_adapter_details(client):
    instance = mock_instance()
    instance.send_command_rcon.side_effect = RuntimeError("synthetic-private-stderr")
    with patch_runtime_resource('docker_mc_manager') as manager:
        manager.get_instance.return_value = instance
        response = client.post("/servers/vanilla/rcon", json={"command": "list"}, headers=auth_headers())
    assert response.status_code == 502
    assert "synthetic-private-stderr" not in response.text
    instance.send_command_rcon.assert_awaited_once()


def test_unauthenticated_command_has_no_execution(client):
    with patch_runtime_resource('docker_mc_manager') as manager:
        response = client.post("/servers/vanilla/rcon", json={"command": "list"})
    assert response.status_code == 401
    manager.get_instance.assert_not_called()


@pytest.mark.parametrize(("exists", "healthy", "expected"), [(False, False, 404), (True, False, 409), (True, True, 204)])
def test_empty_message_still_checks_target_without_sending(client, exists, healthy, expected):
    instance = mock_instance(exists=exists, healthy=healthy)
    with patch_runtime_resource('docker_mc_manager') as manager:
        manager.get_instance.return_value = instance
        response = client.post("/servers/vanilla/message", json={"message": "\n\n"}, headers=auth_headers())
    assert response.status_code == expected
    instance.send_command_rcon.assert_not_called()
