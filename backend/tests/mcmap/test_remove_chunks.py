"""Tests for runner.remove_chunks — argv shape, NDJSON parsing, error handling."""

import os
import stat
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from app.mcmap import runner
from app.mcmap.events import MCMAP_REMOVE_CHUNKS_EVENT_ADAPTER


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


async def test_remove_chunks_argv_shape_and_events(fake_owned_dir):
    fake = _write_fake_mcmap(
        "#!/bin/sh\n"
        'echo "$@" > "$0.args"\n'
        'echo \'{"type":"chunk_removed","x":4,"z":15}\'\n'
        'echo \'{"type":"chunk_removed","x":13,"z":22}\'\n'
        'echo \'{"type":"result","removed":2}\'\n'
    )
    tgt = fake_owned_dir / "tgt.mca"
    tgt.write_bytes(b"")
    try:
        with patch.object(runner.settings, "mcmap_binary_path", str(fake)):
            async with runner.remove_chunks(
                target_mca=tgt,
                chunks=[(4, 15), (13, 22)],
                owned_by=fake_owned_dir,
            ) as proc:
                events = [
                    e async for e in proc.events(MCMAP_REMOVE_CHUNKS_EVENT_ADAPTER)
                ]
            assert proc.returncode == 0
        args_text = Path(str(fake) + ".args").read_text()
    finally:
        fake.unlink(missing_ok=True)
        Path(str(fake) + ".args").unlink(missing_ok=True)

    assert "--json" in args_text
    assert "remove-chunks" in args_text
    # No -s flag for remove
    assert "-s " not in args_text
    assert f"-t {tgt}" in args_text
    assert "-c 4,15;13,22" in args_text

    types = [e.type for e in events]
    assert types == ["chunk_removed", "chunk_removed", "result"]
    assert events[-1].removed == 2


async def test_remove_chunks_error_event(fake_owned_dir):
    fake = _write_fake_mcmap(
        "#!/bin/sh\n"
        'echo \'{"type":"error","message":"target missing"}\'\n'
        "exit 1\n"
    )
    tgt = fake_owned_dir / "tgt.mca"
    tgt.write_bytes(b"")
    try:
        with patch.object(runner.settings, "mcmap_binary_path", str(fake)):
            async with runner.remove_chunks(
                target_mca=tgt,
                chunks=[(0, 0)],
                owned_by=fake_owned_dir,
            ) as proc:
                events = [
                    e async for e in proc.events(MCMAP_REMOVE_CHUNKS_EVENT_ADAPTER)
                ]
            assert proc.returncode == 1
    finally:
        fake.unlink(missing_ok=True)

    assert events[-1].type == "error"
    assert events[-1].message == "target missing"


async def test_remove_chunks_empty_list_raises(fake_owned_dir):
    tgt = fake_owned_dir / "tgt.mca"
    tgt.write_bytes(b"")
    with pytest.raises(ValueError):
        async with runner.remove_chunks(
            target_mca=tgt,
            chunks=[],
            owned_by=fake_owned_dir,
        ):
            pass
