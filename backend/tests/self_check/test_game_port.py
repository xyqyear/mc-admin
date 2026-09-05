from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.dynamic_config.configs.self_check import SelfCheckConfig
from app.minecraft import MCServerStatus
from app.self_check.checks.server import check_game_port_consistency

COMPOSE = 'services:\n  mc:\n    ports: ["25517:25565"]\n'


@pytest.fixture
def servers(tmp_path, monkeypatch):
    instances = {}
    records = []
    context = SimpleNamespace(active_servers=AsyncMock(return_value=records))
    monkeypatch.setattr(
        "app.self_check.checks.server.docker_mc_manager",
        SimpleNamespace(get_instance=instances.__getitem__),
    )

    def add(name="survival", content="server-port=25565\n", status=MCServerStatus.EXISTS, compose=COMPOSE):
        data_path = tmp_path / name / "data"
        data_path.mkdir(parents=True)
        if content is not None:
            (data_path / "server.properties").write_text(content)
        instance = SimpleNamespace(
            get_status=AsyncMock(return_value=status),
            get_data_path=lambda: data_path,
            get_compose_file=AsyncMock(return_value=compose),
        )
        instances[name] = instance
        records.append(SimpleNamespace(server_id=name))
        return instance

    return context, add


@pytest.mark.parametrize("environment", [
    "", "    environment: {SERVER_PORT: 25566, SKIP_SERVER_PROPERTIES: true}\n",
    "    environment: {OVERRIDE_SERVER_PROPERTIES: false}\n",
])
async def test_matching_legacy_port_ignores_environment(servers, environment):
    context, add = servers
    add(compose=COMPOSE + environment)
    result, = await check_game_port_consistency(context)
    assert result.status == "passed"
    assert result.evidence["expected_container_port"] == 25565
    assert result.evidence["published_game_port"] == "25517"


async def test_stopped_mismatch_includes_remediation_without_writes(servers):
    context, add = servers
    content = "server-port=25566\nrcon.password=secret-not-for-evidence\n"
    instance = add(content=content, status=MCServerStatus.CREATED)
    result, = await check_game_port_consistency(context)
    assert result.status == "warning"
    assert result.server_id == "survival"
    assert result.evidence["properties_server_port"] == 25566
    assert "25565" in result.remediation[0]
    assert "重启" in result.remediation[0]
    assert "SERVER_PORT" in result.remediation[1]
    assert "secret-not-for-evidence" not in result.model_dump_json()
    assert (instance.get_data_path() / "server.properties").read_text() == content


@pytest.mark.parametrize("status,content,expected", [
    (MCServerStatus.EXISTS, None, "skipped"),
    (MCServerStatus.CREATED, None, "skipped"),
    (MCServerStatus.STARTING, "server-port=25566", "skipped"),
    (MCServerStatus.RUNNING, None, "failed"),
    (MCServerStatus.HEALTHY, None, "failed"),
    (MCServerStatus.HEALTHY, "server-port=25565", "passed"),
])
async def test_lifecycle_states(servers, status, content, expected):
    context, add = servers
    instance = add(content=content, status=status)
    result, = await check_game_port_consistency(context)
    assert result.status == expected
    if expected == "skipped":
        assert result.severity == "info"
        instance.get_compose_file.assert_not_awaited()
    if status == MCServerStatus.STARTING:
        instance.get_status.return_value = MCServerStatus.HEALTHY
        next_result, = await check_game_port_consistency(context)
        assert next_result.status == "warning"


@pytest.mark.parametrize("content", [
    "", "motd=test", "server-port=", "server-port=true", "server-port=secret-invalid",
    "server-port=0", "server-port=65536", "server-port=25565.5",
    "server-port=25565\nserver-port=",
])
async def test_invalid_file_port_is_a_failed_comparison(servers, content):
    context, add = servers
    add(content=content)
    result, = await check_game_port_consistency(context)
    assert (result.severity, result.status) == ("warning", "failed")
    assert result.evidence["error_stage"] == "properties"
    assert "secret-invalid" not in result.model_dump_json()


async def test_properties_comments_whitespace_and_last_value(servers):
    context, add = servers
    add(content="# server-port=123\r\nserver-port=25566\r\n server-port = 25565 \r\n")
    result, = await check_game_port_consistency(context)
    assert result.status == "passed"


@pytest.mark.parametrize("compose", [
    "services: [secret-invalid: [", "services: {}", COMPOSE.replace("25565", "25566"),
    COMPOSE.replace("25565", "25565/udp"),
])
async def test_invalid_compose_is_a_failed_comparison(servers, compose):
    context, add = servers
    add(compose=compose)
    result, = await check_game_port_consistency(context)
    assert result.status == "failed"
    assert result.evidence["error_stage"] == "compose"
    assert "secret-invalid" not in result.model_dump_json()


async def test_per_server_errors_do_not_abort_the_scan(servers):
    context, add = servers
    unreadable = add("unreadable")
    path = unreadable.get_data_path() / "server.properties"
    path.unlink()
    path.mkdir()
    add("mismatched", content="server-port=25566")
    broken = add("unavailable")
    broken.get_status.side_effect = RuntimeError("private diagnostic detail")
    results = await check_game_port_consistency(context)
    assert [(item.server_id, item.status) for item in results] == [
        ("unreadable", "failed"), ("mismatched", "warning"), ("unavailable", "failed"),
    ]
    assert "private diagnostic detail" not in results[-1].model_dump_json()


async def test_empty_scan_passes(servers):
    context, _ = servers
    result, = await check_game_port_consistency(context)
    assert result.status == "passed"


def test_existing_self_check_config_enables_new_check_by_default():
    config = SelfCheckConfig.model_validate({"checks": {"dns_drift": False}})
    assert config.is_check_enabled("server.game_port_consistency")
    config.checks.server_game_port_consistency = False
    assert "server.game_port_consistency" not in config.enabled_check_ids()
