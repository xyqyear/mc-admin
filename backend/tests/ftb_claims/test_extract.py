import json
import stat
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from app.config import get_settings
from app.ftb_claims import extract_claims_for_server
from app.mcmap import runner
from tests.support.mcmap import build_minimal_world

pytestmark = [pytest.mark.binary('fd')]


def _write_fake_mcmap(payload: dict, directory: Path) -> Path:
    p = directory / "mcmap-result.sh"
    payload = {
        "mcmap_extract_ftb_claims_version": 1,
        "world_dir": "/tmp/world",
        **payload,
    }
    teams = payload.get("teams", [])
    claims = sum(len(team.get("claims", [])) for team in teams)
    line = json.dumps(
        {
            "type": "result",
            "detected_format": payload["detected_format"],
            "teams": len(teams),
            "claims": claims,
            "dimensions": len(payload.get("dimensions", [])),
            "data": payload,
        }
    ).replace("'", "'\\''")
    p.write_text("#!/bin/sh\n" f"echo '{line}'\n")
    p.chmod(p.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return p


def _write_fake_mcmap_error(message: str, directory: Path) -> Path:
    p = directory / "mcmap-error.sh"
    line = json.dumps({"type": "error", "message": message}).replace("'", "'\\''")
    p.write_text("#!/bin/sh\n" f"echo '{line}'\n")
    p.chmod(p.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return p


@pytest.fixture
def world_data_path():
    with tempfile.TemporaryDirectory(prefix="ftb_extract_") as d:
        data_path = Path(d)
        build_minimal_world(data_path)
        yield data_path


async def test_unavailable_when_mcmap_reports_no_data(world_data_path):
    fake = _write_fake_mcmap_error("could not detect FTB claim format in world directory", world_data_path)
    with patch.object(runner.get_settings(), "mcmap_binary_path", str(fake)):
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
    fake = _write_fake_mcmap(payload, world_data_path)
    with patch.object(runner.get_settings(), "mcmap_binary_path", str(fake)):
        result = await extract_claims_for_server(world_data_path)
    fake.unlink()

    assert result.available is True
    assert result.detected_format == "snbt"

    # Dimension resolution
    by_id = {d.ftb_id: d for d in result.dimensions}
    overworld = by_id["minecraft:overworld"]
    assert overworld.region_dir_relpath == "world/region"
    assert overworld.exists_on_disk is True

    nether = by_id["minecraft:the_nether"]
    assert nether.region_dir_relpath == "world/DIM-1/region"

    mining = by_id["allthemodium:mining"]
    assert mining.region_dir_relpath is None
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


async def test_extract_does_not_require_full_dimension_scan(world_data_path, monkeypatch):
    payload = {
        "detected_format": "snbt",
        "world_dir": str(world_data_path / "world"),
        "dimensions": [{"id": "minecraft:overworld", "folder": ".", "exists": True}],
        "teams": [],
    }
    fake = _write_fake_mcmap(payload, world_data_path)
    monkeypatch.setattr(get_settings(), "fd_binary_path", Path("/missing/fd"))
    with patch.object(runner.get_settings(), "mcmap_binary_path", str(fake)):
        result = await extract_claims_for_server(world_data_path)
    fake.unlink()

    assert result.available is True
    assert result.dimensions[0].region_dir_relpath == "world/region"


async def test_extract_error_other_than_no_data_propagates(world_data_path):
    from app.ftb_claims import FtbExtractError

    fake = _write_fake_mcmap_error("world directory not found: /nonexistent", world_data_path)
    with (
        patch.object(runner.get_settings(), 'mcmap_binary_path', str(fake)),
        pytest.raises(FtbExtractError),
    ):
        await extract_claims_for_server(world_data_path)
    fake.unlink()


async def test_extract_rejects_malformed_mcmap_payload(world_data_path):
    from app.ftb_claims import FtbExtractError

    payload = {
        "detected_format": "snbt",
        "world_dir": str(world_data_path / "world"),
        "dimensions": [{"id": "minecraft:overworld", "folder": ".", "exists": True}],
        "teams": [
            {
                "id": "team-uuid-1",
                "name": "alice",
                "type": "player",
                "owner": None,
                "members": [],
                "claims": [
                    {
                        "dim": "minecraft:overworld",
                        "cx": "0",
                        "cz": 0,
                        "force_loaded": False,
                    }
                ],
            }
        ],
    }
    fake = _write_fake_mcmap(payload, world_data_path)
    with (
        patch.object(runner.get_settings(), 'mcmap_binary_path', str(fake)),
        pytest.raises(FtbExtractError, match='invalid JSON event'),
    ):
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
    fake = _write_fake_mcmap(payload, world_data_path)
    with patch.object(runner.get_settings(), "mcmap_binary_path", str(fake)):
        result = await extract_claims_for_server(world_data_path)
    fake.unlink()
    assert result.teams[0].display_name == "12345678"


@pytest.mark.binary("mcmap")
async def test_real_snbt_claims_preserve_team_dimensions_and_protected_chunks(world_data_path):
    world = world_data_path / "world"
    claims = world / "ftbchunks"
    teams = world / "ftbteams" / "party"
    claims.mkdir()
    teams.mkdir(parents=True)
    team_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    claims_file = claims / f"{team_id}.snbt"
    claims_file.write_text('''{
        chunks: {
            "minecraft:overworld": [
                {x: -1, z: 0, force_loaded: 0L},
                {x: 0, z: 0, force_loaded: 1L},
                {x: 1, z: 1, force_loaded: 0L}
            ],
            "minecraft:the_nether": [{x: 5, z: 5, force_loaded: 0L}],
            "custom:missing": [{x: 3, z: 4, force_loaded: 1L}]
        }
    }''')
    team_file = teams / f"{team_id}.snbt"
    team_file.write_text('''{
        type: "party",
        properties: {"ftbteams:display_name": "共同家园"},
        ranks: {"11111111-2222-3333-4444-555555555555": "owner"}
    }''')
    before = {path: path.read_bytes() for path in (claims_file, team_file)}

    result = await extract_claims_for_server(world_data_path)

    assert result.available and result.detected_format == "snbt"
    assert len(result.teams) == 1
    team = result.teams[0]
    assert team.id == team_id and team.display_name == "共同家园"
    assert team.type == "party" and team.total_chunks == 5
    assert team.owner is not None and team.owner.uuid == "11111111-2222-3333-4444-555555555555"
    overworld = [cluster for cluster in team.clusters if cluster.region_dir_relpath == "world/region"]
    assert {frozenset(cluster.chunks) for cluster in overworld} == {
        frozenset({(-1, 0), (0, 0)}), frozenset({(1, 1)}),
    }
    connected = next(cluster for cluster in overworld if (-1, 0) in cluster.chunks)
    assert connected.force_loaded == [(0, 0)]
    assert set(connected.regions) == {(-1, 0), (0, 0)}
    unresolved = next(cluster for cluster in team.clusters if cluster.region_dir_relpath is None)
    assert unresolved.chunks == [(3, 4)] and unresolved.force_loaded == [(3, 4)]
    assert any(cluster.region_dir_relpath == "world/DIM-1/region" for cluster in team.clusters)
    assert all(path.read_bytes() == content for path, content in before.items())
