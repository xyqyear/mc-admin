"""Tests for runner.replace_chunks — argv shape, NDJSON parsing, error handling.

These tests use a fake mcmap shell script (the same pattern as test_runner.py).
A separate end-to-end byte-level test against real mcmap is out of scope: Phase 6
covers chunk merge with a real binary via the orchestrator integration tests.
"""

import os
import stat
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


async def test_replace_chunks_argv_shape_and_events(fake_owned_dir):
    fake = _write_fake_mcmap(
        "#!/bin/sh\n"
        'echo "$@" > "$0.args"\n'
        'echo \'{"type":"chunk_replaced","x":4,"z":15,"source_kind":"external"}\'\n'
        'echo \'{"type":"chunk_replaced","x":13,"z":22,"source_kind":"inline"}\'\n'
        'echo \'{"type":"result","replaced":2}\'\n'
    )
    src = fake_owned_dir / "src.mca"
    tgt = fake_owned_dir / "tgt.mca"
    src.write_bytes(b"")
    tgt.write_bytes(b"")
    try:
        with patch.object(runner.settings, "mcmap_binary_path", str(fake)):
            async with runner.replace_chunks(
                source_mca=src,
                target_mca=tgt,
                chunks=[(4, 15), (13, 22)],
                owned_by=fake_owned_dir,
            ) as proc:
                events = [e async for e in proc]
            assert proc.returncode == 0
        args_text = Path(str(fake) + ".args").read_text()
    finally:
        fake.unlink(missing_ok=True)
        Path(str(fake) + ".args").unlink(missing_ok=True)

    assert "--json" in args_text
    assert "replace-chunks" in args_text
    assert f"-s {src}" in args_text
    assert f"-t {tgt}" in args_text
    # Coords serialized as one semicolon-separated -c argument
    assert "-c 4,15;13,22" in args_text

    types = [e["type"] for e in events]
    assert types == ["chunk_replaced", "chunk_replaced", "result"]
    assert events[0]["x"] == 4 and events[0]["z"] == 15
    assert events[0]["source_kind"] == "external"
    assert events[-1]["replaced"] == 2


async def test_replace_chunks_single_chunk(fake_owned_dir):
    fake = _write_fake_mcmap(
        "#!/bin/sh\n"
        'echo "$@" > "$0.args"\n'
        'echo \'{"type":"chunk_replaced","x":0,"z":0,"source_kind":"empty"}\'\n'
        'echo \'{"type":"result","replaced":1}\'\n'
    )
    src = fake_owned_dir / "src.mca"
    tgt = fake_owned_dir / "tgt.mca"
    src.write_bytes(b"")
    tgt.write_bytes(b"")
    try:
        with patch.object(runner.settings, "mcmap_binary_path", str(fake)):
            async with runner.replace_chunks(
                source_mca=src,
                target_mca=tgt,
                chunks=[(0, 0)],
                owned_by=fake_owned_dir,
            ) as proc:
                events = [e async for e in proc]
            assert proc.returncode == 0
        args_text = Path(str(fake) + ".args").read_text()
    finally:
        fake.unlink(missing_ok=True)
        Path(str(fake) + ".args").unlink(missing_ok=True)

    assert "-c 0,0" in args_text
    assert events[-1]["replaced"] == 1


async def test_replace_chunks_error_event_and_nonzero_exit(fake_owned_dir):
    fake = _write_fake_mcmap(
        "#!/bin/sh\n"
        'echo \'{"type":"error","message":"chunk (32,0) out of range"}\'\n'
        "exit 1\n"
    )
    src = fake_owned_dir / "src.mca"
    tgt = fake_owned_dir / "tgt.mca"
    src.write_bytes(b"")
    tgt.write_bytes(b"")
    try:
        with patch.object(runner.settings, "mcmap_binary_path", str(fake)):
            async with runner.replace_chunks(
                source_mca=src,
                target_mca=tgt,
                chunks=[(32, 0)],
                owned_by=fake_owned_dir,
            ) as proc:
                events = [e async for e in proc]
            assert proc.returncode == 1
    finally:
        fake.unlink(missing_ok=True)

    assert events == [{"type": "error", "message": "chunk (32,0) out of range"}]


async def test_replace_chunks_empty_list_raises(fake_owned_dir):
    src = fake_owned_dir / "src.mca"
    tgt = fake_owned_dir / "tgt.mca"
    src.write_bytes(b"")
    tgt.write_bytes(b"")
    with pytest.raises(ValueError):
        async with runner.replace_chunks(
            source_mca=src,
            target_mca=tgt,
            chunks=[],
            owned_by=fake_owned_dir,
        ):
            pass
