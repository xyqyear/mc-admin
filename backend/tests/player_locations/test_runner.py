import os
import stat
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from app.player_locations import runner
from app.mcmap.events import MCMAP_PLAYERS_EVENT_ADAPTER


def _write_fake_mcmap(content: str) -> Path:
    fd, path = tempfile.mkstemp(suffix=".sh", prefix="fake_players_mcmap_")
    os.close(fd)
    p = Path(path)
    p.write_text(content)
    p.chmod(p.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return p


@pytest.fixture
def fake_owned_dir():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


async def test_extract_players_yields_result_event(fake_owned_dir):
    fake = _write_fake_mcmap(
        "#!/bin/sh\n"
        'echo \'{"type":"result","players":0,"skipped":0,"dimensions":0,"data":{"mcmap_extract_players_version":1,"world_dir":"/tmp/world","dimensions":[],"players":[],"skipped":[]}}\'\n'
    )
    with patch.object(runner.settings, "mcmap_binary_path", str(fake)):
        async with runner.extract_players(
            world_dir=Path("/tmp/world"),
            owned_by=fake_owned_dir,
        ) as proc:
            events = [e async for e in proc.events(MCMAP_PLAYERS_EVENT_ADAPTER)]
        assert proc.returncode == 0
    fake.unlink()
    assert events[0].type == "result"
    assert events[0].players == 0


async def test_extract_players_passes_world_arg(fake_owned_dir):
    fake = _write_fake_mcmap(
        "#!/bin/sh\n"
        'echo "$@" > "$0.args"\n'
        'echo \'{"type":"result","players":0,"skipped":0,"dimensions":0,"data":{"mcmap_extract_players_version":1,"world_dir":"/tmp/world","dimensions":[],"players":[],"skipped":[]}}\'\n'
    )
    world = fake_owned_dir / "world"
    with patch.object(runner.settings, "mcmap_binary_path", str(fake)):
        async with runner.extract_players(
            world_dir=world,
            owned_by=fake_owned_dir,
        ) as proc:
            _ = [e async for e in proc.events(MCMAP_PLAYERS_EVENT_ADAPTER)]
        assert proc.returncode == 0
    args_text = Path(str(fake) + ".args").read_text()
    fake.unlink()
    Path(str(fake) + ".args").unlink()
    assert "extract-players" in args_text
    assert "--world" in args_text
    assert str(world) in args_text
    assert "--json" in args_text
