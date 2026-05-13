import json
import os
import stat
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from app.ftb_claims import extract_claims_for_server, runner


def _write_fake_mcmap(payload: dict) -> Path:
    fd, path = tempfile.mkstemp(suffix=".sh", prefix="fake_ftb_mcmap_")
    os.close(fd)
    p = Path(path)
    line = json.dumps({"type": "result", "data": payload}).replace("'", "'\\''")
    p.write_text("#!/bin/sh\n" f"echo '{line}'\n")
    p.chmod(p.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return p


def _write_fake_mcmap_error(message: str) -> Path:
    fd, path = tempfile.mkstemp(suffix=".sh", prefix="fake_ftb_mcmap_err_")
    os.close(fd)
    p = Path(path)
    line = json.dumps({"type": "error", "message": message}).replace("'", "'\\''")
    p.write_text("#!/bin/sh\n" f"echo '{line}'\n")
    p.chmod(p.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return p


def _build_minimal_world(data_path: Path) -> None:
    (data_path / "server.properties").write_text("level-name=world\n")
    world = data_path / "world"
    (world / "region").mkdir(parents=True)
    (world / "region" / "r.0.0.mca").write_bytes(b"")
    (world / "level.dat").write_bytes(b"")
    nether = world / "DIM-1"
    (nether / "region").mkdir(parents=True)
    (nether / "region" / "r.0.0.mca").write_bytes(b"")


@pytest.fixture
def world_data_path():
    with tempfile.TemporaryDirectory(prefix="ftb_extract_") as d:
        data_path = Path(d)
        _build_minimal_world(data_path)
        yield data_path


async def test_unavailable_when_mcmap_reports_no_data(world_data_path):
    fake = _write_fake_mcmap_error("could not detect FTB claim format in world directory")
    with patch.object(runner.settings, "mcmap_binary_path", str(fake)):
        result = await extract_claims_for_server(world_data_path)
    fake.unlink()
    assert result.available is False
    assert result.teams == []
    assert result.dimensions == []


async def test_unavailable_when_no_world_roots():
    with tempfile.TemporaryDirectory() as d:
        # Empty data_path — no world roots discoverable.
        result = await extract_claims_for_server(Path(d))
    assert result.available is False


async def test_extract_resolves_dim_and_groups_clusters(world_data_path):
    payload = {
        "detected_format": "snbt",
        "world_dir": str(world_data_path / "world"),
        "dimensions": [
            {"id": "minecraft:overworld", "folder": ".", "exists": True},
            {"id": "minecraft:the_nether", "folder": "DIM-1", "exists": True},
            # Modded dim that doesn't exist in our layout — must show up
            # in the response with region_dir_relpath=None.
            {
                "id": "allthemodium:mining",
                "folder": "dimensions/allthemodium/mining",
                "exists": False,
            },
        ],
        "teams": [
            {
                "id": "team-uuid-1",
                "name": "alice",
                "type": "player",
                "owner": {
                    "uuid": "team-uuid-1",
                    "name": "alice",
                    "rank": "owner",
                },
                "members": [
                    {"uuid": "team-uuid-1", "name": "alice", "rank": "owner"}
                ],
                "claims": [
                    # Two connected chunks in the overworld.
                    {"dim": "minecraft:overworld", "cx": 0, "cz": 0, "force_loaded": False},
                    {"dim": "minecraft:overworld", "cx": 1, "cz": 0, "force_loaded": True},
                    # One chunk in the nether — separate cluster.
                    {"dim": "minecraft:the_nether", "cx": 5, "cz": 5, "force_loaded": False},
                    # One chunk in unresolved modded dim.
                    {"dim": "allthemodium:mining", "cx": 0, "cz": 0, "force_loaded": False},
                ],
            },
            {
                # per_team_nbt-style team: name null, owner.name has it.
                "id": "8559re",
                "name": None,
                "type": "player",
                "owner": {
                    "uuid": "abcd",
                    "name": "8559re",
                    "rank": "owner",
                },
                "members": [{"uuid": "abcd", "name": "8559re", "rank": "owner"}],
                "claims": [
                    {"dim": "minecraft:overworld", "cx": 100, "cz": 100, "force_loaded": False}
                ],
            },
        ],
    }
    fake = _write_fake_mcmap(payload)
    with patch.object(runner.settings, "mcmap_binary_path", str(fake)):
        result = await extract_claims_for_server(world_data_path)
    fake.unlink()

    assert result.available is True
    assert result.detected_format == "snbt"

    # Dimension resolution
    by_id = {d.ftb_id: d for d in result.dimensions}
    overworld = by_id["minecraft:overworld"]
    assert overworld.region_dir_relpath == "world/region"
    assert overworld.label == "Overworld"
    assert overworld.exists_on_disk is True

    nether = by_id["minecraft:the_nether"]
    assert nether.region_dir_relpath == "world/DIM-1/region"
    assert nether.label == "Nether"

    mining = by_id["allthemodium:mining"]
    assert mining.region_dir_relpath is None
    assert mining.label is None
    assert mining.exists_on_disk is False

    # Teams
    by_name = {t.display_name: t for t in result.teams}
    alice = by_name["alice"]
    # Three clusters: overworld (2 chunks), nether (1), unresolved (1).
    assert len(alice.clusters) == 3
    assert alice.total_chunks == 4
    overworld_cluster = next(
        c for c in alice.clusters if c.region_dir_relpath == "world/region"
    )
    assert sorted(overworld_cluster.chunks) == [(0, 0), (1, 0)]
    assert overworld_cluster.force_loaded == [(1, 0)]
    unresolved = next(c for c in alice.clusters if c.region_dir_relpath is None)
    assert unresolved.chunks == [(0, 0)]

    # Display-name fallback chain (owner.name when team.name is null).
    eight = by_name["8559re"]
    assert eight.id == "8559re"
    assert eight.type == "player"


async def test_extract_error_other_than_no_data_propagates(world_data_path):
    from app.ftb_claims import FtbExtractError

    fake = _write_fake_mcmap_error("world directory not found: /nonexistent")
    with patch.object(runner.settings, "mcmap_binary_path", str(fake)):
        with pytest.raises(FtbExtractError):
            await extract_claims_for_server(world_data_path)
    fake.unlink()


async def test_display_name_falls_back_to_id_prefix(world_data_path):
    payload = {
        "detected_format": "snbt",
        "world_dir": str(world_data_path / "world"),
        "dimensions": [
            {"id": "minecraft:overworld", "folder": ".", "exists": True}
        ],
        "teams": [
            {
                "id": "1234567890abcdef-anonymous",
                "name": None,
                "type": "party",
                "owner": None,
                "members": [{"name": None}],
                "claims": [
                    {"dim": "minecraft:overworld", "cx": 0, "cz": 0, "force_loaded": False}
                ],
            }
        ],
    }
    fake = _write_fake_mcmap(payload)
    with patch.object(runner.settings, "mcmap_binary_path", str(fake)):
        result = await extract_claims_for_server(world_data_path)
    fake.unlink()
    assert result.teams[0].display_name == "12345678"
