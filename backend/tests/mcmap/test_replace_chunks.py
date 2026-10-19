"""Real chunk replacement plus controlled protocol failure boundaries."""

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from app.mcmap import runner
from app.mcmap.events import MCMAP_REPLACE_CHUNKS_EVENT_ADAPTER
from tests.support.mcmap import write_fake_mcmap
from tests.support.regions import chunk_value, region_bytes


@pytest.fixture
def fake_owned_dir():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


async def test_replace_chunks_error_event_and_nonzero_exit(fake_owned_dir):
    fake = write_fake_mcmap(
        "#!/bin/sh\n"
        'echo \'{"type":"error","message":"chunk (32,0) out of range"}\'\n'
        "exit 1\n"
    )
    src = fake_owned_dir / "源 区块.mca"
    tgt = fake_owned_dir / "目标 区块.mca"
    src.write_bytes(b"")
    tgt.write_bytes(b"")
    try:
        with patch.object(runner.get_settings(), "mcmap_binary_path", str(fake)):
            async with runner.replace_chunks(
                source_mca=src,
                target_mca=tgt,
                chunks=[(32, 0)],
                owned_by=fake_owned_dir,
            ) as proc:
                events = [
                    e async for e in proc.events(MCMAP_REPLACE_CHUNKS_EVENT_ADAPTER)
                ]
            assert proc.returncode == 1
    finally:
        fake.unlink(missing_ok=True)

    assert events[-1].type == "error"
    assert events[-1].message == "chunk (32,0) out of range"


async def test_replace_chunks_empty_list_raises(fake_owned_dir):
    src = fake_owned_dir / "源 区块.mca"
    tgt = fake_owned_dir / "目标 区块.mca"
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


@pytest.mark.binary("mcmap")
@pytest.mark.parametrize("selected", [[0], [0, 1]])
async def test_real_replacement_changes_only_selected_chunks(tmp_path, selected):
    source = tmp_path / "源 区块.mca"
    target = tmp_path / "目标 区块.mca"
    source.write_bytes(region_bytes(["source zero", "source one", "unselected source"]))
    target.write_bytes(region_bytes(["live zero", "live one", "preserved live"]))
    source_before = source.read_bytes()
    async with runner.replace_chunks(
        source_mca=source, target_mca=target,
        chunks=[(index, 0) for index in selected], owned_by=tmp_path,
    ) as process:
        events = [event async for event in process.events(MCMAP_REPLACE_CHUNKS_EVENT_ADAPTER)]
    assert process.returncode == 0
    assert events[-1].type == "result" and events[-1].replaced == len(selected)
    assert chunk_value(target, 0) == "source zero"
    assert chunk_value(target, 1) == ("source one" if 1 in selected else "live one")
    assert chunk_value(target, 2) == "preserved live"
    assert source.read_bytes() == source_before
