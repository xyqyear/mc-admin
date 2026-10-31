import asyncio
import logging
from unittest.mock import Mock

import pytest

from app.mcmap.events import MCMAP_RENDER_EVENT_ADAPTER, MCMapProtocolError
from app.mcmap.runner import MCMapProcess
from app.minecraft import DockerMCManager
from app.minecraft.instance import MCInstance
from app.servers import port_utils
from tests.fixtures.test_utils import create_mc_server_compose_yaml
from tests.support.runtime import set_runtime_resource


def invalid_compose(secret: str) -> str:
    return f"services:\n  mc:\n    environment:\n      TOKEN:\n        - {secret}\n"


async def test_compose_validation_does_not_log_authored_values(tmp_path, caplog):
    secret = "synthetic-compose-password-value"
    instance = MCInstance(tmp_path, "synthetic")
    with (
        caplog.at_level(logging.DEBUG),
        pytest.raises(ValueError, match="Invalid compose YAML") as failure,
    ):
        await instance.create(invalid_compose(secret))
    assert secret not in str(failure.value) + caplog.text
    assert "ValidationError" in caplog.text
    assert not instance.get_project_path().exists()


async def test_port_scan_skips_compose_replaced_after_discovery_without_logging_secrets(monkeypatch, tmp_path, caplog):
    secret = "synthetic-port-scan-password-value"
    manager = DockerMCManager(tmp_path)
    for name, content in (
        ("invalid", create_mc_server_compose_yaml("invalid", 25566, 25576)),
        ("valid", create_mc_server_compose_yaml("valid", 25565, 25575)),
    ):
        directory = tmp_path / name
        directory.mkdir()
        (directory / "docker-compose.yml").write_text(content)
    discover = manager.get_all_instances

    async def discover_before_replacement():
        instances = await discover()
        (tmp_path / "invalid/docker-compose.yml").write_text(invalid_compose(secret))
        return instances

    monkeypatch.setattr(manager, "get_all_instances", discover_before_replacement)
    set_runtime_resource(monkeypatch, "docker_mc_manager", manager)
    with caplog.at_level(logging.DEBUG):
        assert await port_utils.get_server_used_ports() == {25565, 25575}
    assert secret not in caplog.text
    assert "ValidationError" in caplog.text


async def test_mcmap_invalid_json_keeps_protocol_error_without_logging_payload(caplog):
    secret = "synthetic-mcmap-invalid-json-password"
    stdout = asyncio.StreamReader()
    stdout.feed_data(f"not-json {secret}\n".encode())
    stdout.feed_eof()
    process = Mock(spec=asyncio.subprocess.Process)
    process.stdout = stdout
    process.stderr = None
    with (
        caplog.at_level(logging.DEBUG),
        pytest.raises(MCMapProtocolError, match="mcmap emitted an invalid JSON event") as failure,
    ):
        _ = [event async for event in MCMapProcess(process).events(MCMAP_RENDER_EVENT_ADAPTER)]
    assert secret not in str(failure.value) + caplog.text
    assert "ValidationError" in caplog.text
