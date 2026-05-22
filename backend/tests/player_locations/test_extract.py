import json
import os
import stat
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from app.config import settings
from app.models import UserPublic
from app.player_locations import (
    PlayerLocationExtractError,
    extract_player_locations_for_server,
    normalize_uuid,
    runner,
)
from app.routers.servers import world_restore


def _test_user() -> UserPublic:
    return UserPublic(
        id=1,
        username="test",
        created_at=datetime.now(timezone.utc),
    )


def _write_fake_mcmap(payload: dict) -> Path:
    fd, path = tempfile.mkstemp(suffix=".sh", prefix="fake_players_mcmap_")
    os.close(fd)
    p = Path(path)
    payload = {
        "mcmap_extract_players_version": 1,
        "world_dir": "/tmp/world",
        **payload,
    }
    line = json.dumps(
        {
            "type": "result",
            "players": len(payload.get("players", [])),
            "skipped": len(payload.get("skipped", [])),
            "dimensions": len(payload.get("dimensions", [])),
            "data": payload,
        }
    ).replace("'", "'\\''")
    p.write_text("#!/bin/sh\n" f"echo '{line}'\n")
    p.chmod(p.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return p


def _write_fake_mcmap_error(message: str) -> Path:
    fd, path = tempfile.mkstemp(suffix=".sh", prefix="fake_players_mcmap_err_")
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
    with tempfile.TemporaryDirectory(prefix="players_extract_") as d:
        data_path = Path(d)
        _build_minimal_world(data_path)
        yield data_path


def test_normalize_uuid_accepts_dashed_and_dashless():
    assert (
        normalize_uuid("0b4c4192-8eb3-4f0b-9022-8e2cb2ee6fc0")
        == "0b4c41928eb34f0b90228e2cb2ee6fc0"
    )
    assert (
        normalize_uuid("0B4C41928EB34F0B90228E2CB2EE6FC0")
        == "0b4c41928eb34f0b90228e2cb2ee6fc0"
    )
    assert normalize_uuid("not-a-uuid") is None


async def test_extract_resolves_dimensions_and_keeps_skipped(world_data_path):
    payload = {
        "mcmap_extract_players_version": 1,
        "world_dir": str(world_data_path / "world"),
        "dimensions": [
            {"id": "minecraft:overworld", "folder": ".", "exists": True},
            {"id": "minecraft:the_nether", "folder": "DIM-1", "exists": True},
            {"id": "allthemodium:mining", "folder": "dimensions/allthemodium/mining", "exists": False},
        ],
        "players": [
            {
                "id": "0b4c4192-8eb3-4f0b-9022-8e2cb2ee6fc0",
                "id_kind": "uuid",
                "source": "playerdata/0b4c4192-8eb3-4f0b-9022-8e2cb2ee6fc0.dat",
                "storage": "playerdata",
                "data_version": 3955,
                "dim": "minecraft:overworld",
                "pos": {"x": -10.5, "y": 73.0, "z": 20.25},
            },
            {
                "id": "LegacyName",
                "id_kind": "name",
                "source": "players/LegacyName.dat",
                "storage": "legacy_players",
                "dim": "minecraft:the_nether",
                "pos": {"x": 1, "y": 64, "z": 2},
            },
            {
                "id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
                "id_kind": "uuid",
                "source": "players/data/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee.dat",
                "storage": "players_data",
                "dim": "allthemodium:mining",
                "pos": {"x": 3, "y": 80, "z": 4},
            },
        ],
        "skipped": [
            {
                "source": "playerdata/example_cyclic.dat",
                "storage": "playerdata",
                "reason": "missing_pos",
            }
        ],
    }
    fake = _write_fake_mcmap(payload)
    with patch.object(runner.settings, "mcmap_binary_path", str(fake)):
        result = await extract_player_locations_for_server(world_data_path)
    fake.unlink()

    by_id = {d.dimension_id: d for d in result.dimensions}
    assert by_id["minecraft:overworld"].region_dir_relpath == "world/region"
    assert by_id["minecraft:the_nether"].region_dir_relpath == "world/DIM-1/region"
    assert by_id["allthemodium:mining"].region_dir_relpath is None

    by_source = {p.source: p for p in result.players}
    overworld = by_source["playerdata/0b4c4192-8eb3-4f0b-9022-8e2cb2ee6fc0.dat"]
    assert overworld.uuid == "0b4c41928eb34f0b90228e2cb2ee6fc0"
    assert overworld.region_dir_relpath == "world/region"
    assert overworld.pos.x == -10.5

    legacy = by_source["players/LegacyName.dat"]
    assert legacy.uuid is None
    assert legacy.region_dir_relpath == "world/DIM-1/region"

    unresolved = by_source["players/data/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee.dat"]
    assert unresolved.region_dir_relpath is None

    assert result.skipped[0].reason == "missing_pos"


async def test_extract_does_not_require_full_dimension_scan(world_data_path, monkeypatch):
    payload = {
        "mcmap_extract_players_version": 1,
        "world_dir": str(world_data_path / "world"),
        "dimensions": [{"id": "minecraft:overworld", "folder": ".", "exists": True}],
        "players": [],
        "skipped": [],
    }
    fake = _write_fake_mcmap(payload)
    monkeypatch.setattr(settings, "fd_binary_path", Path("/missing/fd"))
    with patch.object(runner.settings, "mcmap_binary_path", str(fake)):
        result = await extract_player_locations_for_server(world_data_path)
    fake.unlink()

    assert result.dimensions[0].region_dir_relpath == "world/region"


async def test_extract_error_propagates(world_data_path):
    fake = _write_fake_mcmap_error("world directory not found: /nonexistent")
    with patch.object(runner.settings, "mcmap_binary_path", str(fake)):
        with pytest.raises(PlayerLocationExtractError):
            await extract_player_locations_for_server(world_data_path)
    fake.unlink()


async def test_extract_rejects_malformed_mcmap_payload(world_data_path):
    payload = {
        "world_dir": str(world_data_path / "world"),
        "dimensions": [{"id": "minecraft:overworld", "folder": ".", "exists": True}],
        "players": [
            {
                "id": "0b4c4192-8eb3-4f0b-9022-8e2cb2ee6fc0",
                "id_kind": "uuid",
                "source": "playerdata/0b4c4192-8eb3-4f0b-9022-8e2cb2ee6fc0.dat",
                "storage": "playerdata",
                "dim": "minecraft:overworld",
                "pos": {"x": 1, "z": 2},
            }
        ],
        "skipped": [],
    }
    fake = _write_fake_mcmap(payload)
    with patch.object(runner.settings, "mcmap_binary_path", str(fake)):
        with pytest.raises(PlayerLocationExtractError, match="invalid JSON event"):
            await extract_player_locations_for_server(world_data_path)
    fake.unlink()


async def test_endpoint_returns_player_locations(world_data_path):
    class FakeInstance:
        def get_data_path(self):
            return world_data_path

        async def exists(self):
            return True

    class FakeDocker:
        def get_instance(self, server_id: str):
            return FakeInstance()

    payload = {
        "dimensions": [{"id": "minecraft:overworld", "folder": ".", "exists": True}],
        "players": [
            {
                "id": "0b4c4192-8eb3-4f0b-9022-8e2cb2ee6fc0",
                "id_kind": "uuid",
                "source": "playerdata/0b4c4192-8eb3-4f0b-9022-8e2cb2ee6fc0.dat",
                "storage": "playerdata",
                "dim": "minecraft:overworld",
                "pos": {"x": 1, "y": 64, "z": 2},
            }
        ],
        "skipped": [],
    }
    fake = _write_fake_mcmap(payload)
    with (
        patch.object(runner.settings, "mcmap_binary_path", str(fake)),
        patch.object(world_restore, "docker_mc_manager", FakeDocker()),
    ):
        result = await world_restore.get_player_locations("srv1", _=_test_user())
    fake.unlink()
    assert result.players[0].region_dir_relpath == "world/region"
