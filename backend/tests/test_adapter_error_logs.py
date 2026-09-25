import asyncio
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.mcmap.events import MCMAP_RENDER_EVENT_ADAPTER, MCMapProtocolError
from app.mcmap.runner import MCMapProcess
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


async def test_port_scan_skips_invalid_compose_without_logging_secrets(monkeypatch, tmp_path, caplog):
    secret = "synthetic-port-scan-password-value"
    invalid = SimpleNamespace(
        get_name=lambda: "invalid",
        get_compose_file_path=AsyncMock(return_value=tmp_path / "invalid.yml"),
        get_compose_file=AsyncMock(return_value=invalid_compose(secret)),
    )
    valid = SimpleNamespace(
        get_name=lambda: "valid",
        get_compose_file_path=AsyncMock(return_value=tmp_path / "valid.yml"),
        get_compose_file=AsyncMock(return_value=create_mc_server_compose_yaml("valid", 25565, 25575)),
    )
    set_runtime_resource(monkeypatch, 'docker_mc_manager', SimpleNamespace(get_all_instances=AsyncMock(return_value=[invalid, valid])))
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
