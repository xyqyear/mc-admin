import asyncio
import socket
import struct
import threading
import time
from dataclasses import replace

import docker
import pytest

from app.minecraft.docker.commands import (
    DockerCommands,
    ServerUnavailable,
    _read_output,
)
from app.minecraft.docker.reader import ContainerState, DockerReader
from tests.fixtures.test_utils import MINECRAFT_IMAGE, OWNER_LABEL, OwnedDockerResources


@pytest.fixture
async def command_container(tmp_path, request):
    resources = OwnedDockerResources(tmp_path)
    name = resources.name("exec")
    resources.containers.append(name)
    client = docker.from_env()
    try:
        container = await asyncio.to_thread(
            client.containers.run, MINECRAFT_IMAGE,
            name=name, labels={OWNER_LABEL: resources.owner}, detach=True,
            entrypoint=["/bin/sh", "-c"], command=["exec sleep 300"],
            user=str(getattr(request, "param", 0)), network_mode="none", read_only=True,
            tmpfs={"/tmp": "rw,exec,mode=1777", "/data": "rw,mode=1777"}, cap_drop=["ALL"],
            healthcheck={"test": ["CMD", "true"], "interval": 100_000_000},
        )
        for _ in range(100):
            await asyncio.to_thread(container.reload)
            if container.attrs["State"].get("Health", {}).get("Status") == "healthy":
                break
            await asyncio.sleep(0.05)
        assert container.attrs["State"]["Health"]["Status"] == "healthy"
        assert container.id is not None
        state = ContainerState(container.id, container.attrs["State"]["StartedAt"], True, "healthy")
        adapter = DockerCommands()
        try:
            yield adapter, state, container
        finally:
            await adapter.close()
    finally:
        client.close()
        await resources.cleanup()


async def run(adapter, state, *argv, duration=1.0):
    return await adapter.execute(state, list(argv), execution_timeout=duration, timeout=duration + 3, kind="test")


@pytest.mark.docker
@pytest.mark.parametrize("command_container", [0, 1000], indirect=True)
async def test_real_command_output_arguments_and_failure(command_container):
    adapter, state, container = command_container
    value = '中文 "quoted" $(touch /tmp/injected);\nsecond \\ line'
    assert await run(adapter, state, "printf", "%s", value) == value
    assert await run(adapter, state, "sh", "-c", "printf out; printf secret >&2") == "out"
    with pytest.raises(RuntimeError, match="退出码 23") as error:
        await run(adapter, state, "sh", "-c", "echo synthetic-secret >&2; exit 23")
    assert "synthetic-secret" not in str(error.value)
    assert (await asyncio.to_thread(container.exec_run, ["test", "!", "-e", "/tmp/injected"])).exit_code == 0


@pytest.mark.docker
async def test_tools_selected_before_execution_without_retry(command_container):
    adapter, state, container = command_container
    setup = '''mkdir /tmp/tools
ln -s /bin/sh /tmp/tools/sh
printf '#!/bin/sh\necho GNU >> /tmp/calls\nexec /usr/bin/timeout "$@"\n' > /tmp/tools/gnutimeout
printf '#!/bin/sh\necho fallback >> /tmp/calls\nexec /usr/bin/timeout "$@"\n' > /tmp/tools/timeout
chmod +x /tmp/tools/gnutimeout /tmp/tools/timeout
'''
    assert (await asyncio.to_thread(container.exec_run, ["sh", "-c", setup])).exit_code == 0
    original = container.client.api.exec_create

    # Only the image PATH is varied; the adapter still executes through the real Engine.
    from unittest.mock import patch

    from docker.api import APIClient

    def create(api, *args, **kwargs):
        kwargs["environment"] = {"PATH": "/tmp/tools"}
        return original(*args, **kwargs)

    with patch.object(APIClient, "exec_create", create):
        assert await run(adapter, state, "/bin/echo", "ok") == "ok\n"
        with pytest.raises(RuntimeError, match="退出码 7"):
            await run(adapter, state, "/bin/sh", "-c", "exit 7")
        await asyncio.to_thread(container.exec_run, ["/bin/rm", "/tmp/tools/gnutimeout"])
        assert await run(adapter, state, "/bin/echo", "fallback") == "fallback\n"
        await asyncio.to_thread(container.exec_run, ["/bin/rm", "/tmp/tools/timeout"])
        with pytest.raises(RuntimeError, match="退出码 127"):
            await run(adapter, state, "/bin/touch", "/tmp/unbounded")
    calls = await asyncio.to_thread(container.exec_run, ["cat", "/tmp/calls"])
    assert calls.output.decode().splitlines() == ["GNU", "GNU", "fallback"]
    assert (await asyncio.to_thread(container.exec_run, ["test", "!", "-e", "/tmp/unbounded"])).exit_code == 0


@pytest.mark.docker
@pytest.mark.parametrize("script", [
    'sleep 30 | cat',
    'trap "" TERM; while :; do sleep 1; done',
])
async def test_timeout_stops_command_group_without_stopping_container(command_container, script):
    adapter, state, container = command_container
    with pytest.raises(TimeoutError):
        await run(adapter, state, "sh", "-c", 'echo $$ > /tmp/command-pid; ps -o pgid= -p $$ > /tmp/command-group; ' + script, duration=0.2)
    pid = (await asyncio.to_thread(container.exec_run, ["cat", "/tmp/command-pid"])).output.strip().decode()
    check = await asyncio.to_thread(container.exec_run, ["sh", "-c", 'test ! -e /proc/"$1"/stat || test "$(cut -d " " -f3 /proc/"$1"/stat)" = Z', "check", pid])
    assert check.exit_code == 0
    group = (await asyncio.to_thread(container.exec_run, ["cat", "/tmp/command-group"])).output.strip().decode()
    processes = (await asyncio.to_thread(container.exec_run, ["ps", "-eo", "pgid=,stat="])).output.decode()
    assert all(pgid != group or status.startswith("Z") for pgid, status in (line.split() for line in processes.splitlines()))
    await asyncio.to_thread(container.reload)
    assert container.attrs["State"]["Running"]
    assert await run(adapter, state, "echo", "alive") == "alive\n"


@pytest.mark.docker
async def test_cancel_and_close_drain_owned_work(command_container):
    adapter, state, container = command_container
    task = asyncio.create_task(run(adapter, state, "sh", "-c", "echo ready > /tmp/ready; sleep 30", duration=0.4))
    while (await asyncio.to_thread(container.exec_run, ["test", "-e", "/tmp/ready"])).exit_code:
        await asyncio.sleep(0.01)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await adapter.close()
    assert not adapter._pending
    with pytest.raises(RuntimeError, match="已关闭"):
        await run(adapter, state, "touch", "/tmp/after-close")
    assert (await asyncio.to_thread(container.exec_run, ["test", "!", "-e", "/tmp/after-close"])).exit_code == 0


@pytest.mark.docker
async def test_changed_instance_cannot_execute(command_container):
    adapter, state, container = command_container
    with pytest.raises(ServerUnavailable):
        await run(adapter, replace(state, started_at="old"), "touch", "/tmp/wrong-instance")
    assert (await asyncio.to_thread(container.exec_run, ["test", "!", "-e", "/tmp/wrong-instance"])).exit_code == 0


@pytest.mark.parametrize("payload", [b"", b"\x01\0", struct.pack(">BxxxI", 1, 4) + b"ab"])
async def test_output_disconnect_never_returns_partial_success(payload):
    reader, writer = socket.socketpair()
    try:
        writer.sendall(payload)
        writer.shutdown(socket.SHUT_WR)
        if not payload:
            assert await asyncio.to_thread(_read_output, reader, time.monotonic() + 1) == b""
        else:
            with pytest.raises(RuntimeError, match="意外关闭"):
                await asyncio.to_thread(_read_output, reader, time.monotonic() + 1)
    finally:
        reader.close()
        writer.close()


async def test_silent_output_connection_has_absolute_deadline():
    reader, writer = socket.socketpair()
    try:
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(asyncio.to_thread(_read_output, reader, time.monotonic() + 0.05), 1)
    finally:
        reader.close()
        writer.close()


async def test_queued_cancellation_does_not_execute_and_close_drains_threads(monkeypatch):
    adapter = DockerCommands()
    entered = threading.Event()
    release = threading.Event()
    calls = []
    lock = threading.Lock()

    def execute(container, argv, *args):
        with lock:
            calls.append(argv)
            if len(calls) == 4:
                entered.set()
        assert release.wait(5)
        return "done"

    monkeypatch.setattr(adapter, "_execute", execute)
    state = ContainerState("test", "start", True, "healthy")
    active = [asyncio.create_task(run(adapter, state, str(i))) for i in range(4)]
    try:
        assert await asyncio.to_thread(entered.wait, 2)
        queued = asyncio.create_task(run(adapter, state, "cancelled"))
        await asyncio.sleep(0)
        queued.cancel()
        with pytest.raises(asyncio.CancelledError):
            await queued
        closing = asyncio.create_task(adapter.close())
        await asyncio.sleep(0)
        assert not closing.done()
        release.set()
        assert await asyncio.gather(*active) == ["done"] * 4
        await closing
        assert ["cancelled"] not in calls
        assert not adapter._pending
    finally:
        release.set()
        await asyncio.gather(*active, return_exceptions=True)
        await adapter.close()


@pytest.mark.docker
async def test_slow_command_does_not_block_docker_reader(command_container):
    adapter, state, _ = command_container
    reader = DockerReader()
    task = asyncio.create_task(run(adapter, state, "sleep", "2", duration=3))
    try:
        await asyncio.sleep(0.1)
        await asyncio.wait_for(reader.list_containers(), 1)
        assert not task.done()
        assert await task == ""
    finally:
        await asyncio.gather(task, return_exceptions=True)
        await reader.close()


@pytest.mark.parametrize("duration", [0, -1, float("inf"), float("nan")])
async def test_invalid_timeout_cannot_start_unbounded_command(duration):
    adapter = DockerCommands()
    try:
        with pytest.raises(RuntimeError, match="正有限"):
            await run(adapter, ContainerState("unused", "start", True, "healthy"), "true", duration=duration)
    finally:
        await adapter.close()
