import asyncio
import threading
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.minecraft.docker.reader import (
    ONE_OFF,
    PROJECT,
    SERVICE,
    WORKING_DIR,
    DockerReader,
    ProjectTarget,
)
from app.minecraft.status import MCServerStatus


class Engine:
    def __init__(self):
        self.containers_by_id = {}
        self.processes = {"Titles": ["PID", "COMMAND"], "Processes": [["100", "tini"], ["101", "java"]]}
        self.closed = False

    def add(self, identifier="main", *, project="custom", path="/servers/alpha", service="mc", name="mc-alpha", status="running", health="healthy", one_off=False):
        labels = {PROJECT: project, WORKING_DIR: path, SERVICE: service, ONE_OFF: str(one_off)}
        self.containers_by_id[identifier] = {
            "Id": identifier, "Names": [f"/{name}"], "Labels": labels,
            "Config": {"Labels": labels},
            "State": {"Status": status, "StartedAt": "2026-11-01T00:00:00Z", "Health": {"Status": health}},
        }

    def containers(self, **kwargs):
        return deepcopy(list(self.containers_by_id.values()))

    def inspect_container(self, identifier):
        return deepcopy(self.containers_by_id[identifier])

    def top(self, identifier, **kwargs):
        return self.processes

    def close(self):
        self.closed = True


@pytest.fixture
async def reader(monkeypatch):
    engine = Engine()
    monkeypatch.setattr("docker.from_env", lambda **kwargs: SimpleNamespace(api=engine, close=engine.close))
    adapter = DockerReader()
    try:
        yield adapter, engine
    finally:
        await adapter.close()


TARGET = ProjectTarget(Path("/servers/alpha"), "mc-alpha", "custom")


@pytest.mark.parametrize(("status", "health", "expected"), [
    ("created", "", MCServerStatus.CREATED),
    ("exited", "healthy", MCServerStatus.CREATED),
    ("restarting", "unhealthy", MCServerStatus.CREATED),
    ("running", "", MCServerStatus.RUNNING),
    ("running", "unhealthy", MCServerStatus.RUNNING),
    ("running", "starting", MCServerStatus.STARTING),
    ("running", "healthy", MCServerStatus.HEALTHY),
])
async def test_structured_project_status(reader, status, health, expected):
    adapter, engine = reader
    engine.add(status=status, health=health)
    observed = await adapter.observe(TARGET)
    assert observed.status == expected
    assert observed.container.container_id == "main"


async def test_custom_project_and_other_services_keep_project_status(reader):
    adapter, engine = reader
    assert (await adapter.observe(TARGET)).status == MCServerStatus.EXISTS
    engine.add("sidecar", service="helper", name="helper")
    result = await adapter.observe(TARGET)
    assert result.status == MCServerStatus.RUNNING
    assert result.container is None
    engine.add(status="exited", health="healthy")
    assert (await adapter.observe(TARGET)).status == MCServerStatus.RUNNING


async def test_label_values_containing_equals_do_not_break_health(reader):
    adapter, engine = reader
    engine.add()
    engine.containers_by_id["main"]["Labels"].update({"mode": "CUSTOM:FAMILY=VANILLA", "encoded": "abc==", "empty": ""})
    assert (await adapter.observe(TARGET)).status == MCServerStatus.HEALTHY


async def test_foreign_projects_and_one_off_containers_are_not_claimed(reader):
    adapter, engine = reader
    engine.add("foreign-path", path="/elsewhere/alpha")
    engine.add("foreign-project", project="other")
    engine.add("one-off", one_off=True)
    result = await adapter.observe(TARGET)
    assert result.status == MCServerStatus.EXISTS
    assert result.container is None


async def test_ambiguous_or_changed_ownership_is_not_reported_as_stopped(reader, monkeypatch):
    adapter, engine = reader
    engine.add(name="mc-other")
    with pytest.raises(RuntimeError, match="不匹配"):
        await adapter.observe(TARGET)
    engine.add()
    listed = await adapter.list_containers()
    engine.containers_by_id["main"]["Config"]["Labels"][WORKING_DIR] = "/elsewhere"
    with pytest.raises(RuntimeError, match="归属"):
        await adapter.observe(TARGET, listed)


async def test_java_pid_is_not_container_init_and_ambiguity_fails(reader):
    adapter, engine = reader
    assert await adapter.java_pid("main") == 101
    engine.processes["Processes"].append(["102", "java"])
    with pytest.raises(RuntimeError, match="Java"):
        await adapter.java_pid("main")


async def test_cancellation_and_close_wait_for_real_sdk_completion(reader, monkeypatch):
    adapter, engine = reader
    entered, release = threading.Event(), threading.Event()

    def blocked(**kwargs):
        entered.set()
        assert release.wait(5)
        assert not engine.closed
        return []

    monkeypatch.setattr(engine, "containers", blocked)
    pending = asyncio.create_task(adapter.list_containers())
    closing = None
    try:
        async with asyncio.timeout(2):
            while not entered.is_set():
                await asyncio.sleep(0.005)
        pending.cancel()
        closing = asyncio.create_task(adapter.close())
        await asyncio.sleep(0)
        pending.cancel()
        assert not pending.done() and not closing.done()
    finally:
        release.set()
        await asyncio.gather(pending, *( [closing] if closing else []), return_exceptions=True)
    assert pending.cancelled()
    assert engine.closed
    with pytest.raises(RuntimeError, match="关闭"):
        await adapter.list_containers()
