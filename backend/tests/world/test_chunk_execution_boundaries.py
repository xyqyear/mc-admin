import asyncio
import json
import os
import sys
from pathlib import Path

import pytest

from app.config import get_settings
from app.mcmap.types import MCMapError
from app.minecraft import DockerMCManager
from app.snapshots import SnapshotService
from app.snapshots.restic import ResticClient
from app.world.scope_execution import RestoreScopeExecutor


def executor(tmp_path: Path) -> RestoreScopeExecutor:
    return RestoreScopeExecutor(SnapshotService(
        ResticClient(str(tmp_path / "repository"), binary_path="restic"),
        DockerMCManager(tmp_path / "servers"),
    ))


@pytest.mark.parametrize("operation", ["replace", "remove"])
@pytest.mark.parametrize(("outcome", "expected"), [
    ("error", "owned adapter error"),
    ("missing", "处理了 None 个区块"),
    ("count", "处理了 1 个区块"),
    ("exit", "退出码为 7"),
    ("success", None),
])
async def test_chunk_cli_requires_matching_result_and_successful_exit(
    tmp_path: Path, monkeypatch, operation, outcome, expected,
):
    events = []
    if outcome == "error":
        events = [{"type": "error", "message": "owned adapter error"}]
    elif outcome != "missing":
        events = [{"type": "result", "replaced" if operation == "replace" else "removed":
                   1 if outcome == "count" else 2}]
    adapter = tmp_path / "owned-chunk-adapter"
    adapter.write_text(
        f"#!{sys.executable}\nimport sys\n"
        + "".join(f"print({json.dumps(json.dumps(event))}, flush=True)\n" for event in events)
        + f"sys.exit({7 if outcome == 'exit' else 0})\n"
    )
    adapter.chmod(0o700)
    monkeypatch.setattr(get_settings(), "mcmap_binary_path", str(adapter))
    data = tmp_path / "data"
    data.mkdir()
    runner = executor(tmp_path)
    if operation == "replace":
        command = runner.replace_selected_chunks(
            source_mca=tmp_path / "source.mca", target_mca=data / "region/r.-1.-1.mca",
            chunks=[(0, 0), (1, 1)], owned_by=data,
        )
    else:
        command = runner.remove_selected_chunks(
            target_mca=data / "region/r.-1.-1.mca", chunks=[(0, 0), (1, 1)], owned_by=data,
        )
    if expected is None:
        await command
    else:
        with pytest.raises(MCMapError, match=expected):
            await command


@pytest.mark.parametrize("operation", ["replace", "remove"])
async def test_chunk_cli_cancellation_stops_the_owned_process_before_return(
    tmp_path: Path, monkeypatch, operation,
):
    ready = tmp_path / "process-ready"
    adapter = tmp_path / "owned-chunk-adapter"
    adapter.write_text(
        f"#!{sys.executable}\nimport pathlib, os, time\n"
        f"pathlib.Path({str(ready)!r}).write_text(str(os.getpid()))\n"
        "print('{\"type\":\"progress\",\"phase\":\"owned-wait\"}', flush=True)\n"
        "while True: time.sleep(0.01)\n"
    )
    adapter.chmod(0o700)
    monkeypatch.setattr(get_settings(), "mcmap_binary_path", str(adapter))
    data = tmp_path / "data"
    data.mkdir()
    runner = executor(tmp_path)
    command = runner.replace_selected_chunks(
        source_mca=tmp_path / "source.mca", target_mca=data / "region/r.0.0.mca",
        chunks=[(0, 0)], owned_by=data,
    ) if operation == "replace" else runner.remove_selected_chunks(
        target_mca=data / "region/r.0.0.mca", chunks=[(0, 0)], owned_by=data,
    )
    task = asyncio.create_task(command)
    try:
        async with asyncio.timeout(3):
            while not ready.exists():
                await asyncio.sleep(0.01)
        pid = int(ready.read_text())
        os.kill(pid, 0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 3)
        with pytest.raises(ProcessLookupError):
            os.kill(pid, 0)
    finally:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
