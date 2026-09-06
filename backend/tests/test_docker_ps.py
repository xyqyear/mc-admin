import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.minecraft.docker.manager import (
    ComposeManager,
    DockerComposePsParsed,
    DockerManager,
    DockerPsParsed,
)


def ps_payload(labels: str, health: str = "healthy") -> dict[str, Any]:
    return {
        "Command": '"/image/scripts/start"',
        "CreatedAt": "2026-09-06 12:07:13 +0800 CST",
        "ID": "0dc811d6d077",
        "Image": "itzg/minecraft-server:java25",
        "Labels": labels,
        "LocalVolumes": "0",
        "Mounts": "/servers/test/data",
        "Names": "mc-test",
        "Networks": "test_default",
        "Ports": "25565/tcp",
        "RunningFor": "6 minutes ago",
        "Size": "0B",
        "State": "running",
        "Status": f"Up 6 minutes ({health})",
        "ExitCode": 0,
        "Health": health,
        "Name": "mc-test",
        "Project": "test",
        "Publishers": [],
        "Service": "mc",
    }


@pytest.mark.parametrize("parser", ["docker", "compose"])
@pytest.mark.parametrize(
    ("labels", "expected"),
    [
        ("", {}),
        ("com.docker.compose.depends_on=", {"com.docker.compose.depends_on": ""}),
        (
            "mode=CUSTOM:FAMILY=VANILLA,empty=,encoded=abc==,service=mc",
            {
                "mode": "CUSTOM:FAMILY=VANILLA",
                "empty": "",
                "encoded": "abc==",
                "service": "mc",
            },
        ),
    ],
)
def test_ps_preserves_label_values(
    parser: str, labels: str, expected: dict[str, str]
):
    data = ps_payload(labels)
    if parser == "docker":
        parsed = DockerPsParsed.from_docker_ps(data)
    else:
        parsed = DockerComposePsParsed.from_docker_compose_ps(data)

    assert parsed.labels == expected
    assert parsed.state == "running"


@pytest.mark.parametrize(
    ("health", "healthy", "starting"),
    [("healthy", True, False), ("starting", False, True), ("unhealthy", False, False)],
)
async def test_compose_health_with_equals_in_label_values(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    health: str,
    healthy: bool,
    starting: bool,
):
    manager = ComposeManager(tmp_path)
    output = ps_payload(
        "com.docker.compose.depends_on=,mode=CUSTOM:FAMILY=VANILLA", health
    )
    command = AsyncMock(return_value=json.dumps(output) + "\n")
    monkeypatch.setattr(manager, "run_compose_command", command)

    assert await manager.healthy("mc") is healthy
    assert await manager.starting("mc") is starting
    assert not await manager.healthy("missing-service")
    command.assert_awaited_with("ps", "--no-trunc", "--format", "json")


async def test_docker_ps_lists_containers_with_equals_in_label_values(
    monkeypatch: pytest.MonkeyPatch,
):
    output = ps_payload("mode=CUSTOM:FAMILY=VANILLA,empty=")
    command = AsyncMock(return_value=json.dumps(output) + "\n")
    monkeypatch.setattr(DockerManager, "run_sub_command", command)

    containers = await DockerManager.ps()

    assert len(containers) == 1
    assert containers[0].names == "mc-test"
    assert containers[0].labels == {"mode": "CUSTOM:FAMILY=VANILLA", "empty": ""}
    command.assert_awaited_once_with("ps", "--no-trunc", "--format", "json")
