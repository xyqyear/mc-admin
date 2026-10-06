import asyncio
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from app.mcmap import runner
from app.mcmap.events import (
    MCMAP_DOWNLOAD_CLIENT_EVENT_ADAPTER,
    MCMAP_FTB_CLAIMS_EVENT_ADAPTER,
    MCMAP_GEN_PALETTE_EVENT_ADAPTER,
    MCMAP_PLAYERS_EVENT_ADAPTER,
    MCMAP_PRUNE_EVENT_ADAPTER,
    MCMAP_RENDER_EVENT_ADAPTER,
    MCMapChunksPrunedEvent,
    MCMapProtocolError,
    MCMapPruneProgressEvent,
    MCMapPruneRegionDirEvent,
    MCMapPruneResultEvent,
    MCMapRegionPrunedEvent,
    MCMapRenderRegionEvent,
)
from tests.support.mcmap import owned_chown_args, read_fake_mcmap_args, write_fake_mcmap


@pytest.fixture
def fake_owned_dir():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


async def test_render_parses_ndjson_events(fake_owned_dir):
    fake = write_fake_mcmap(
        "#!/bin/sh\n"
        'printf "%s\\0" "$@" > "$0.args"\n'
        'echo \'{"type":"region","x":0,"z":0,"status":"rendered","output":"/x.png"}\'\n'
        'echo \'{"type":"region","x":1,"z":0,"status":"missing"}\'\n'
        'echo \'{"type":"result","mode":"split","regions_saved":1,"output":"./tiles","elapsed_ms":12}\'\n'
    )
    try:
        with patch.object(runner.get_settings(), "mcmap_binary_path", str(fake)):
            events = []
            async with runner.render(
                palette=fake_owned_dir / "调色 文件.json",
                output_dir=fake_owned_dir / "地图 输出",
                mcas=[fake_owned_dir / "世界 区域" / "r.0.0.mca", fake_owned_dir / "世界 区域" / "r.1.0.mca"],
                threads=2,
                owned_by=fake_owned_dir,
            ) as proc:
                async for ev in proc.events(MCMAP_RENDER_EVENT_ADAPTER):
                    events.append(ev)
            assert proc.returncode == 0
        args = read_fake_mcmap_args(fake)
    finally:
        fake.unlink(missing_ok=True)
        Path(f"{fake}.args").unlink(missing_ok=True)
    assert args == [
        "--json", "render", "-p", str(fake_owned_dir / "调色 文件.json"),
        "-o", str(fake_owned_dir / "地图 输出"), "--split", "--preserve-mtime", "-j", "2",
        "-r", str(fake_owned_dir / "世界 区域" / "r.0.0.mca"),
        "-r", str(fake_owned_dir / "世界 区域" / "r.1.0.mca"),
        *owned_chown_args(fake_owned_dir),
    ]

    types = [e.type for e in events]
    assert types == ["region", "region", "result"]
    assert isinstance(events[0], MCMapRenderRegionEvent)
    assert isinstance(events[1], MCMapRenderRegionEvent)
    assert events[0].x == 0
    assert events[0].status == "rendered"
    assert events[1].status == "missing"


async def test_runner_rejects_malformed_lines(fake_owned_dir):
    fake = write_fake_mcmap(
        "#!/bin/sh\n"
        "echo 'not json'\n"
        'echo \'{"type":"result"}\'\n'
    )
    with patch.object(runner.get_settings(), "mcmap_binary_path", str(fake)):
        async with runner.render(
            palette=Path("/tmp/p.json"),
            output_dir=Path("/tmp/o"),
            mcas=[],
            threads=1,
            owned_by=fake_owned_dir,
        ) as proc:
            with pytest.raises(MCMapProtocolError):
                _ = [e async for e in proc.events(MCMAP_RENDER_EVENT_ADAPTER)]
    fake.unlink()


async def test_runner_terminate_is_idempotent(fake_owned_dir):
    fake = write_fake_mcmap(
        "#!/bin/sh\n"
        # Sleep so we can terminate it mid-run
        "sleep 30\n"
    )
    with patch.object(runner.get_settings(), "mcmap_binary_path", str(fake)):
        async with runner.render(
            palette=Path("/tmp/p.json"),
            output_dir=Path("/tmp/o"),
            mcas=[],
            threads=1,
            owned_by=fake_owned_dir,
        ) as proc:
            await proc.terminate()
            await proc.terminate()  # second call must not raise
            assert proc.returncode is not None
    fake.unlink()


async def test_runner_terminates_on_context_exit_even_if_caller_breaks(
    fake_owned_dir,
):
    fake = write_fake_mcmap("#!/bin/sh\nsleep 30\n")
    with patch.object(runner.get_settings(), "mcmap_binary_path", str(fake)):
        async with runner.render(
            palette=Path("/tmp/p.json"),
            output_dir=Path("/tmp/o"),
            mcas=[],
            threads=1,
            owned_by=fake_owned_dir,
        ) as proc:
            pass  # exit without iterating
        assert proc.returncode is not None
    fake.unlink()


async def test_download_client_args_passed_through(fake_owned_dir):
    fake = write_fake_mcmap(
        "#!/bin/sh\n"
        'printf "%s\\0" "$@" > "$0.args"\n'
        'echo \'{"type":"result","version":"1.21.4","target":"/tmp/client.jar","bytes":123,"sha1":"abc","move_method":"rename"}\'\n'
    )
    target = fake_owned_dir / "客户端 版本.jar"
    try:
        with patch.object(runner.get_settings(), "mcmap_binary_path", str(fake)):
            async with runner.download_client(
                "1.21.4", target, owned_by=fake_owned_dir
            ) as proc:
                events = [e async for e in proc.events(MCMAP_DOWNLOAD_CLIENT_EVENT_ADAPTER)]
            assert proc.returncode == 0
        args = read_fake_mcmap_args(fake)
    finally:
        fake.unlink(missing_ok=True)
        Path(f"{fake}.args").unlink(missing_ok=True)
    assert args == ["--json", "download-client", "1.21.4", str(target), *owned_chown_args(fake_owned_dir)]
    assert events[-1].type == "result"


async def test_gen_palette_passes_level_dat_when_set(fake_owned_dir):
    fake = write_fake_mcmap(
        "#!/bin/sh\n"
        'printf "%s\\0" "$@" > "$0.args"\n'
        'echo \'{"type":"result","output":"/tmp/palette.json","entries":10,"counters":{}}\'\n'
    )
    out = fake_owned_dir / "调色 文件.json"
    level_dat = fake_owned_dir / "世界 存档" / "level.dat"
    try:
        with patch.object(runner.get_settings(), "mcmap_binary_path", str(fake)):
            async with runner.gen_palette(
                packs=[fake_owned_dir / "客户端 一.jar", fake_owned_dir / "资源 包.zip"],
                output=out,
                level_dat=level_dat,
                owned_by=fake_owned_dir,
            ) as proc:
                _ = [e async for e in proc.events(MCMAP_GEN_PALETTE_EVENT_ADAPTER)]
            assert proc.returncode == 0
        args = read_fake_mcmap_args(fake)
    finally:
        fake.unlink(missing_ok=True)
        Path(f"{fake}.args").unlink(missing_ok=True)
    assert args == [
        "--json", "gen-palette", "-o", str(out), "--level-dat", str(level_dat),
        "-p", str(fake_owned_dir / "客户端 一.jar"), "-p", str(fake_owned_dir / "资源 包.zip"),
        *owned_chown_args(fake_owned_dir),
    ]


async def test_gen_palette_omits_level_dat_when_none(fake_owned_dir):
    fake = write_fake_mcmap(
        "#!/bin/sh\n"
        'printf "%s\\0" "$@" > "$0.args"\n'
        'echo \'{"type":"result","output":"/tmp/palette.json","entries":10,"counters":{}}\'\n'
    )
    try:
        with patch.object(runner.get_settings(), "mcmap_binary_path", str(fake)):
            async with runner.gen_palette(
                packs=[fake_owned_dir / "client.jar"],
                output=fake_owned_dir / "palette.json",
                level_dat=None,
                owned_by=fake_owned_dir,
            ) as proc:
                _ = [e async for e in proc.events(MCMAP_GEN_PALETTE_EVENT_ADAPTER)]
            assert proc.returncode == 0
        args = read_fake_mcmap_args(fake)
    finally:
        fake.unlink(missing_ok=True)
        Path(f"{fake}.args").unlink(missing_ok=True)
    assert args == [
        "--json", "gen-palette", "-o", str(fake_owned_dir / "palette.json"),
        "-p", str(fake_owned_dir / "client.jar"), *owned_chown_args(fake_owned_dir),
    ]


async def test_prune_inhabited_passes_mode_threshold_and_claims(fake_owned_dir):
    fake = write_fake_mcmap(
        "#!/bin/sh\n"
        'printf "%s\\0" "$@" > "$0.args"\n'
        'echo \'{"type":"result","mode":"chunks","dry_run":true,"region_dirs":1,"regions_scanned":0,"chunks_scanned":0,"chunks_selected":0,"regions_selected":0}\'\n'
    )
    claims = fake_owned_dir / "领地 信息.json"
    claims.write_text("{}")
    try:
        with patch.object(runner.get_settings(), "mcmap_binary_path", str(fake)):
            async with runner.prune_inhabited(
                path=fake_owned_dir / "世界 存档" / "region",
                threshold_ticks=1200,
                mode="chunks",
                dry_run=True,
                owned_by=fake_owned_dir,
                exclude_ftb_claims=claims,
            ) as proc:
                events = [e async for e in proc.events(MCMAP_PRUNE_EVENT_ADAPTER)]
            assert proc.returncode == 0
        args = read_fake_mcmap_args(fake)
    finally:
        fake.unlink(missing_ok=True)
        Path(f"{fake}.args").unlink(missing_ok=True)
    assert args == [
        "--json", "prune-inhabited", str(fake_owned_dir / "世界 存档" / "region"),
        "--threshold", "1200", "--mode", "chunks", "--dry-run",
        "--exclude-ftb-claims", str(claims), *owned_chown_args(fake_owned_dir),
    ]
    assert isinstance(events[-1], MCMapPruneResultEvent)


async def test_prune_adapter_parses_streaming_events():
    lines = [
        b'{"type":"region_dir","path":"world/region","regions":2}',
        b'{"type":"chunks_pruned","region":"world/region/r.0.0.mca","region_x":0,"region_z":0,"chunks":[{"chunk_x":4,"chunk_z":15,"rel_x":4,"rel_z":15,"inhabited_time":480},{"chunk_x":5,"chunk_z":15,"rel_x":5,"rel_z":15,"inhabited_time":481}],"dry_run":true}',
        b'{"type":"region_pruned","region":"world/region/r.1.0.mca","region_x":1,"region_z":0,"chunks":1024,"max_inhabited_time":800,"dry_run":true}',
        b'{"type":"progress","phase":"scan","regions_processed":2,"regions_total":2}',
        b'{"type":"result","mode":"regions","dry_run":true,"region_dirs":1,"regions_scanned":2,"chunks_scanned":1536,"chunks_selected":1025,"regions_selected":2,"claims_loaded":3,"claimed_chunks_protected":3,"chunks_skipped_by_claims":1,"regions_skipped_by_claims":1}',
    ]
    events = [MCMAP_PRUNE_EVENT_ADAPTER.validate_json(line) for line in lines]
    assert isinstance(events[0], MCMapPruneRegionDirEvent)
    assert isinstance(events[1], MCMapChunksPrunedEvent)
    assert len(events[1].chunks) == 2
    assert isinstance(events[2], MCMapRegionPrunedEvent)
    assert isinstance(events[3], MCMapPruneProgressEvent)
    assert isinstance(events[4], MCMapPruneResultEvent)
    assert events[4].mode == "regions"
    assert events[4].chunks_skipped_by_claims == 1


async def test_runner_drains_stderr_while_streaming_stdout_and_bounds_retained_bytes(tmp_path, monkeypatch):
    fake = tmp_path / "noisy-mcmap"
    fake.write_text(
        f"#!{sys.executable}\n"
        "import sys\n"
        "sys.stderr.buffer.write(b'x' * (2 * 1024 * 1024))\n"
        "sys.stderr.write('stderr-tail-marker')\n"
        "sys.stderr.flush()\n"
        'print(\'{"type":"region","x":0,"z":0,"status":"missing"}\', flush=True)\n'
    )
    fake.chmod(0o700)
    monkeypatch.setattr(runner.get_settings(), "mcmap_binary_path", fake)
    monkeypatch.setattr(runner, "MCMAP_STREAM_LIMIT_BYTES", 64 * 1024)
    async with asyncio.timeout(5):
        async with runner.render(palette=tmp_path / "palette.json", output_dir=tmp_path / "tiles", mcas=[], threads=1, owned_by=tmp_path) as process:
            events = [event async for event in process.events(MCMAP_RENDER_EVENT_ADAPTER)]
            retained = await process.stderr()
    assert len(events) == 1 and events[0].type == "region"
    assert process.returncode == 0
    assert len(retained.encode()) == runner.MCMAP_STDERR_LIMIT_BYTES
    assert retained.endswith("stderr-tail-marker")
    assert process._stderr_task is not None and process._stderr_task.done()


async def test_concurrent_termination_reaps_one_owned_process_and_stderr_reader(tmp_path, monkeypatch):
    fake = tmp_path / "hanging-mcmap"
    fake.write_text(
        f"#!{sys.executable}\n"
        "import sys, time\n"
        "sys.stderr.write('still running')\n"
        "sys.stderr.flush()\n"
        'print(\'{"type":"region","x":0,"z":0,"status":"missing"}\', flush=True)\n'
        "time.sleep(30)\n"
    )
    fake.chmod(0o700)
    monkeypatch.setattr(runner.get_settings(), "mcmap_binary_path", fake)
    async with asyncio.timeout(5):
        async with runner.render(palette=tmp_path / "palette.json", output_dir=tmp_path / "tiles", mcas=[], threads=1, owned_by=tmp_path) as process:
            events = process.events(MCMAP_RENDER_EVENT_ADAPTER)
            assert (await anext(events)).type == "region"
            await events.aclose()
            await asyncio.gather(process.terminate(), process.terminate())
            assert process.returncode is not None
            assert process._stderr_task is not None and process._stderr_task.done()
            assert not (Path("/proc") / str(process._proc.pid)).exists()

@pytest.mark.parametrize(
    "command,adapter,result",
    [
        (
            "extract_ftb_claims",
            MCMAP_FTB_CLAIMS_EVENT_ADAPTER,
            '{"type":"result","detected_format":"snbt","teams":0,"claims":0,"dimensions":0,"data":{"mcmap_extract_ftb_claims_version":1,"detected_format":"snbt","world_dir":"/tmp/world","dimensions":[],"teams":[]}}',
        ),
        (
            "extract_players",
            MCMAP_PLAYERS_EVENT_ADAPTER,
            '{"type":"result","players":0,"skipped":0,"dimensions":0,"data":{"mcmap_extract_players_version":1,"world_dir":"/tmp/world","dimensions":[],"players":[],"skipped":[]}}',
        ),
    ],
)
async def test_extraction_cancellation_reaps_live_process(tmp_path, monkeypatch, command, adapter, result):
    fake = tmp_path / "owned-extraction"
    fake.write_text(
        f"#!{sys.executable}\n"
        "import time\n"
        f"print({result!r}, flush=True)\n"
        "time.sleep(30)\n"
    )
    fake.chmod(0o700)
    monkeypatch.setattr(runner.get_settings(), "mcmap_binary_path", fake)
    started = asyncio.Event()
    processes = []

    async def consume():
        async with getattr(runner, command)(tmp_path / "world", owned_by=tmp_path) as process:
            processes.append(process)
            async for event in process.events(adapter):
                assert event.type == "result"
                started.set()

    worker = asyncio.create_task(consume())
    try:
        async with asyncio.timeout(5):
            await started.wait()
            process = processes[0]
            assert process.returncode is None
            assert os.getpgid(process._proc.pid) == process._proc.pid
            worker.cancel()
            with pytest.raises(asyncio.CancelledError):
                await worker
        assert process.returncode is not None
        assert process._stderr_task is not None and process._stderr_task.done()
        assert not (Path("/proc") / str(process._proc.pid)).exists()
    finally:
        if not worker.done():
            worker.cancel()
        await asyncio.gather(worker, return_exceptions=True)
