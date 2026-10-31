"""Tests for runner.remove_chunks — argv shape, NDJSON parsing, error handling."""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from app.mcmap import runner
from app.mcmap.events import MCMAP_REMOVE_CHUNKS_EVENT_ADAPTER
from tests.support.mcmap import write_fake_mcmap
from tests.support.regions import chunk_value, region_bytes


@pytest.fixture
def fake_owned_dir():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


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


@pytest.mark.binary("mcmap")
async def test_real_removal_preserves_unselected_chunks(tmp_path):
    target = tmp_path / "目标 区块.mca"
    target.write_bytes(region_bytes(["selected zero", "preserved one", "selected two"]))
    async with runner.remove_chunks(
        target_mca=target, chunks=[(0, 0), (2, 0)], owned_by=tmp_path,
    ) as process:
        events = [event async for event in process.events(MCMAP_REMOVE_CHUNKS_EVENT_ADAPTER)]
    assert process.returncode == 0
    assert events[-1].type == "result" and events[-1].removed == 2
    assert chunk_value(target, 0) is None and chunk_value(target, 2) is None
    assert chunk_value(target, 1) == "preserved one"
