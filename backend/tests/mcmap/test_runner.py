import os
import stat
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from app.mcmap import runner


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
            async for ev in proc:
                events.append(ev)
        assert proc.returncode == 0
    fake.unlink()

    types = [e["type"] for e in events]
    assert types == ["region", "region", "result"]
    assert events[0]["x"] == 0
    assert events[0]["status"] == "rendered"
    assert events[1]["status"] == "missing"


async def test_runner_skips_malformed_lines(fake_owned_dir):
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
            events = [e async for e in proc]
    fake.unlink()
    # Malformed line skipped, only the JSON object yielded
    assert events == [{"type": "result"}]


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
        'echo \'{"type":"result","version":"1.21.4"}\'\n'
    )
    target = fake_owned_dir / "client.jar"
    with patch.object(runner.settings, "mcmap_binary_path", str(fake)):
        async with runner.download_client(
            "1.21.4", target, owned_by=fake_owned_dir
        ) as proc:
            events = [e async for e in proc]
        assert proc.returncode == 0
    args_text = Path(str(fake) + ".args").read_text()
    fake.unlink()
    Path(str(fake) + ".args").unlink()
    # First two args after the script's own name are --json download-client
    assert "--json" in args_text
    assert "download-client" in args_text
    assert "1.21.4" in args_text
    assert str(target) in args_text
    assert events[-1]["type"] == "result"


async def test_gen_palette_passes_level_dat_when_set(fake_owned_dir):
    fake = _write_fake_mcmap(
        "#!/bin/sh\n"
        'echo "$@" > "$0.args"\n'
        'echo \'{"type":"result"}\'\n'
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
            _ = [e async for e in proc]
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
        'echo \'{"type":"result"}\'\n'
    )
    with patch.object(runner.settings, "mcmap_binary_path", str(fake)):
        async with runner.gen_palette(
            packs=[fake_owned_dir / "client.jar"],
            output=fake_owned_dir / "palette.json",
            level_dat=None,
            owned_by=fake_owned_dir,
        ) as proc:
            _ = [e async for e in proc]
        assert proc.returncode == 0
    args_text = Path(str(fake) + ".args").read_text()
    fake.unlink()
    Path(str(fake) + ".args").unlink()
    assert "gen-palette" in args_text
    assert "--level-dat" not in args_text


# Silence "unused import" for sys; keep available for diagnosing test failures
_ = sys
