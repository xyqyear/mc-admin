import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.minecraft.docker.commands import ServerUnavailable
from app.minecraft.docker.reader import ContainerState, ProjectState
from app.minecraft.instance import MCInstance
from app.minecraft.status import MCServerStatus
from tests.support.runtime import set_runtime_resource


@pytest.fixture
def server(tmp_path, monkeypatch, runtime_config):
    instance = MCInstance(tmp_path, "test")
    data = instance.get_data_path()
    data.mkdir(parents=True)
    (data / "server.properties").write_text("enable-query=true\nquery.port=25565\n")
    target = ContainerState("selected", "started", True, "healthy")
    monkeypatch.setattr(instance, "get_project_state", AsyncMock(return_value=ProjectState(MCServerStatus.HEALTHY, target)))
    execute = AsyncMock()
    set_runtime_resource(monkeypatch, "docker_commands", SimpleNamespace(execute=execute, close=AsyncMock()))
    return instance, execute, runtime_config


@pytest.mark.parametrize(("result", "expected"), [("", []), (" Steve\nAlex\n", ["Steve", "Alex"])])
async def test_query_valid_result_does_not_fall_back(server, result, expected):
    instance, execute, config = server
    execute.return_value = result
    assert await instance.list_players() == expected
    assert execute.await_count == 1
    assert execute.await_args.kwargs["execution_timeout"] == config.players.query.timeout


async def test_query_failure_falls_back_on_same_container(server):
    instance, execute, _ = server
    execute.side_effect = [TimeoutError(), "There are 2 players online: Steve, Alex"]
    assert await instance.list_players() == ["Steve", "Alex"]
    first, second = execute.await_args_list
    assert first.args[0] == second.args[0]
    assert second.args[1] == ["rcon-cli", "list"]


async def test_both_observations_failing_does_not_become_empty_list(server):
    instance, execute, _ = server
    execute.side_effect = [TimeoutError(), RuntimeError("unavailable")]
    with pytest.raises(RuntimeError):
        await instance.list_players()
    assert execute.await_count == 2


@pytest.mark.parametrize("error", [ServerUnavailable("changed"), asyncio.CancelledError()])
async def test_cancel_or_changed_instance_does_not_start_fallback(server, error):
    instance, execute, _ = server
    execute.side_effect = error
    with pytest.raises(type(error)):
        await instance.list_players()
    assert execute.await_count == 1


async def test_rcon_preserves_argument_and_removes_ansi(server):
    instance, execute, _ = server
    command = 'tellraw @a {"text":"中文 $(touch bad) \\\"quote\\\""}'
    execute.return_value = "\x1b[31m结果\x1b[0m\n"
    assert await instance.send_command_rcon(command) == "结果"
    assert execute.await_args.args[1] == ["rcon-cli", command]
