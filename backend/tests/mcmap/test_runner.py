import os
import stat
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from app.mcmap import runner
from app.mcmap.events import (
    MCMAP_DOWNLOAD_CLIENT_EVENT_ADAPTER,
    MCMAP_GEN_PALETTE_EVENT_ADAPTER,
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


def _write_fake_mcmap(content: str) -> Path:
    fd, path = tempfile.mkstemp(suffix=".sh", prefix="fake_mcmap_")
    os.close(fd)
    p = Path(path)
    p.write_text(content)
    p.chmod(p.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return p


@pytest.fixture
def fake_owned_dir():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


async def test_render_parses_ndjson_events(fake_owned_dir):
    fake = _write_fake_mcmap(
        "#!/bin/sh\n"
        'echo \'{"type":"region","x":0,"z":0,"status":"rendered","output":"/x.png"}\'\n'
        'echo \'{"type":"region","x":1,"z":0,"status":"missing"}\'\n'
        'echo \'{"type":"result","mode":"split","regions_saved":1,"output":"./tiles","elapsed_ms":12}\'\n'
    )
    with patch.object(runner.settings, "mcmap_binary_path", str(fake)):
        events = []
        async with runner.render(
            palette=Path("/tmp/p.json"),
            output_dir=Path("/tmp/o"),
            mcas=[Path("/tmp/r.0.0.mca")],
            threads=2,
            owned_by=fake_owned_dir,
        ) as proc:
            async for ev in proc.events(MCMAP_RENDER_EVENT_ADAPTER):
                events.append(ev)
        assert proc.returncode == 0
    fake.unlink()

    types = [e.type for e in events]
    assert types == ["region", "region", "result"]
    assert isinstance(events[0], MCMapRenderRegionEvent)
    assert isinstance(events[1], MCMapRenderRegionEvent)
    assert events[0].x == 0
    assert events[0].status == "rendered"
    assert events[1].status == "missing"


async def test_runner_rejects_malformed_lines(fake_owned_dir):
    fake = _write_fake_mcmap(
        "#!/bin/sh\n"
        "echo 'not json'\n"
        'echo \'{"type":"result"}\'\n'
    )
    with patch.object(runner.settings, "mcmap_binary_path", str(fake)):
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
    fake = _write_fake_mcmap(
        "#!/bin/sh\n"
        # Sleep so we can terminate it mid-run
        "sleep 30\n"
    )
    with patch.object(runner.settings, "mcmap_binary_path", str(fake)):
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
    fake = _write_fake_mcmap("#!/bin/sh\nsleep 30\n")
    with patch.object(runner.settings, "mcmap_binary_path", str(fake)):
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
    fake = _write_fake_mcmap(
        "#!/bin/sh\n"
        'echo "$@" > "$0.args"\n'
        'echo \'{"type":"result","version":"1.21.4","target":"/tmp/client.jar","bytes":123,"sha1":"abc","move_method":"rename"}\'\n'
    )
    target = fake_owned_dir / "client.jar"
    with patch.object(runner.settings, "mcmap_binary_path", str(fake)):
        async with runner.download_client(
            "1.21.4", target, owned_by=fake_owned_dir
        ) as proc:
            events = [e async for e in proc.events(MCMAP_DOWNLOAD_CLIENT_EVENT_ADAPTER)]
        assert proc.returncode == 0
    args_text = Path(str(fake) + ".args").read_text()
    fake.unlink()
    Path(str(fake) + ".args").unlink()
    # First two args after the script's own name are --json download-client
    assert "--json" in args_text
    assert "download-client" in args_text
    assert "1.21.4" in args_text
    assert str(target) in args_text
    assert events[-1].type == "result"


async def test_gen_palette_passes_level_dat_when_set(fake_owned_dir):
    fake = _write_fake_mcmap(
        "#!/bin/sh\n"
        'echo "$@" > "$0.args"\n'
        'echo \'{"type":"result","output":"/tmp/palette.json","entries":10,"counters":{}}\'\n'
    )
    out = fake_owned_dir / "palette.json"
    level_dat = fake_owned_dir / "world" / "level.dat"
    with patch.object(runner.settings, "mcmap_binary_path", str(fake)):
        async with runner.gen_palette(
            packs=[fake_owned_dir / "client.jar"],
            output=out,
            level_dat=level_dat,
            owned_by=fake_owned_dir,
        ) as proc:
            _ = [e async for e in proc.events(MCMAP_GEN_PALETTE_EVENT_ADAPTER)]
        assert proc.returncode == 0
    args_text = Path(str(fake) + ".args").read_text()
    fake.unlink()
    Path(str(fake) + ".args").unlink()
    assert "gen-palette" in args_text
    assert "modern" not in args_text.split()
    assert "--level-dat" in args_text
    assert str(level_dat) in args_text


async def test_gen_palette_omits_level_dat_when_none(fake_owned_dir):
    fake = _write_fake_mcmap(
        "#!/bin/sh\n"
        'echo "$@" > "$0.args"\n'
        'echo \'{"type":"result","output":"/tmp/palette.json","entries":10,"counters":{}}\'\n'
    )
    with patch.object(runner.settings, "mcmap_binary_path", str(fake)):
        async with runner.gen_palette(
            packs=[fake_owned_dir / "client.jar"],
            output=fake_owned_dir / "palette.json",
            level_dat=None,
            owned_by=fake_owned_dir,
        ) as proc:
            _ = [e async for e in proc.events(MCMAP_GEN_PALETTE_EVENT_ADAPTER)]
        assert proc.returncode == 0
    args_text = Path(str(fake) + ".args").read_text()
    fake.unlink()
    Path(str(fake) + ".args").unlink()
    assert "gen-palette" in args_text
    assert "--level-dat" not in args_text


async def test_prune_inhabited_passes_mode_threshold_and_claims(fake_owned_dir):
    fake = _write_fake_mcmap(
        "#!/bin/sh\n"
        'echo "$@" > "$0.args"\n'
        'echo \'{"type":"result","mode":"chunks","dry_run":true,"region_dirs":1,"regions_scanned":0,"chunks_scanned":0,"chunks_selected":0,"regions_selected":0}\'\n'
    )
    claims = fake_owned_dir / "claims.json"
    claims.write_text("{}")
    with patch.object(runner.settings, "mcmap_binary_path", str(fake)):
        async with runner.prune_inhabited(
            path=fake_owned_dir / "world" / "region",
            threshold_ticks=1200,
            mode="chunks",
            dry_run=True,
            owned_by=fake_owned_dir,
            exclude_ftb_claims=claims,
        ) as proc:
            events = [e async for e in proc.events(MCMAP_PRUNE_EVENT_ADAPTER)]
        assert proc.returncode == 0
    args_text = Path(str(fake) + ".args").read_text()
    fake.unlink()
    Path(str(fake) + ".args").unlink()
    assert "prune-inhabited" in args_text
    assert "--threshold" in args_text
    assert "1200" in args_text
    assert "--mode" in args_text
    assert "chunks" in args_text
    assert "--dry-run" in args_text
    assert "--exclude-ftb-claims" in args_text
    assert str(claims) in args_text
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


# Silence "unused import" for sys; keep available for diagnosing test failures
_ = sys
