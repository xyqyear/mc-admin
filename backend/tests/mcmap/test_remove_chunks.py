"""Tests for runner.remove_chunks — argv shape, NDJSON parsing, error handling."""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from app.mcmap import runner
from app.mcmap.events import MCMAP_REMOVE_CHUNKS_EVENT_ADAPTER
from tests.support.mcmap import owned_chown_args, read_fake_mcmap_args, write_fake_mcmap


@pytest.fixture
def fake_owned_dir():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


async def test_remove_chunks_argv_shape_and_events(fake_owned_dir):
    fake = write_fake_mcmap(
        "#!/bin/sh\n"
        'printf "%s\\0" "$@" > "$0.args"\n'
        'echo \'{"type":"chunk_removed","x":4,"z":15}\'\n'
        'echo \'{"type":"chunk_removed","x":13,"z":22}\'\n'
        'echo \'{"type":"result","removed":2}\'\n'
    )
    tgt = fake_owned_dir / "目标 区块.mca"
    tgt.write_bytes(b"")
    try:
        with patch.object(runner.get_settings(), "mcmap_binary_path", str(fake)):
            async with runner.remove_chunks(
                target_mca=tgt,
                chunks=[(4, 15), (13, 22)],
                owned_by=fake_owned_dir,
            ) as proc:
                events = [
                    e async for e in proc.events(MCMAP_REMOVE_CHUNKS_EVENT_ADAPTER)
                ]
            assert proc.returncode == 0
        args = read_fake_mcmap_args(fake)
    finally:
        fake.unlink(missing_ok=True)
        Path(str(fake) + ".args").unlink(missing_ok=True)

    assert args == [
        "--json", "remove-chunks", "-t", str(tgt), "-c", "4,15;13,22",
        *owned_chown_args(fake_owned_dir),
    ]

    types = [e.type for e in events]
    assert types == ["chunk_removed", "chunk_removed", "result"]
    assert events[-1].removed == 2


async def test_remove_chunks_error_event(fake_owned_dir):
    fake = write_fake_mcmap(
        "#!/bin/sh\n"
        'echo \'{"type":"error","message":"target missing"}\'\n'
        "exit 1\n"
    )
    tgt = fake_owned_dir / "目标 区块.mca"
    tgt.write_bytes(b"")
    try:
        with patch.object(runner.get_settings(), "mcmap_binary_path", str(fake)):
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
    tgt = fake_owned_dir / "目标 区块.mca"
    tgt.write_bytes(b"")
    with pytest.raises(ValueError):
        async with runner.remove_chunks(
            target_mca=tgt,
            chunks=[],
            owned_by=fake_owned_dir,
        ):
            pass
