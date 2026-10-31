import json
import stat
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from app.auth.schemas import UserPublic
from app.config import get_settings
from app.mcmap import runner
from app.player_locations import (
    PlayerLocationExtractError,
    extract_player_locations_for_server,
)
from app.players.identity import normalize_uuid
from app.routers.servers import world_restore
from tests.support.mcmap import build_minimal_world
from tests.support.runtime import patch_runtime_resource

pytestmark = [pytest.mark.binary('fd')]


def _test_user() -> UserPublic:
    return UserPublic(
        id=1,
        username="test",
        created_at=datetime.now(UTC),
    )


def _write_fake_mcmap(payload: dict, directory: Path) -> Path:
    p = directory / "mcmap-result.sh"
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


def _write_fake_mcmap_error(message: str, directory: Path) -> Path:
    p = directory / "mcmap-error.sh"
    line = json.dumps({"type": "error", "message": message}).replace("'", "'\\''")
    p.write_text("#!/bin/sh\n" f"echo '{line}'\n")
    p.chmod(p.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return p


@pytest.fixture
def world_data_path():
    with tempfile.TemporaryDirectory(prefix="players_extract_") as d:
        data_path = Path(d)
        build_minimal_world(data_path)
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


@pytest.mark.parametrize(("value", "expected"), [
    ("-0b4C-41928eB34f0b-9022-8E2cb2Ee6fC0-", "0b4c41928eb34f0b90228e2cb2ee6fc0"),
    ("", None),
    ("0b4c41928eb34f0b90228e2cb2ee6fc", None),
    ("0b4c41928eb34f0b90228e2cb2ee6fc00", None),
    ("0b4c41928eb34f0b90228e2cb2ee6fcg", None),
    (" 0b4c41928eb34f0b90228e2cb2ee6fc0", None),
])
def test_normalize_uuid_preserves_identity_input_boundaries(value, expected):
    assert normalize_uuid(value) == expected




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
    fake = _write_fake_mcmap(payload, world_data_path)
    with patch.object(runner.get_settings(), "mcmap_binary_path", str(fake)):
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
    fake = _write_fake_mcmap(payload, world_data_path)
    monkeypatch.setattr(get_settings(), "fd_binary_path", Path("/missing/fd"))
    with patch.object(runner.get_settings(), "mcmap_binary_path", str(fake)):
        result = await extract_player_locations_for_server(world_data_path)
    fake.unlink()

    assert result.dimensions[0].region_dir_relpath == "world/region"


async def test_extract_error_propagates(world_data_path):
    fake = _write_fake_mcmap_error("world directory not found: /nonexistent", world_data_path)
    with (
        patch.object(runner.get_settings(), 'mcmap_binary_path', str(fake)),
        pytest.raises(PlayerLocationExtractError),
    ):
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
    fake = _write_fake_mcmap(payload, world_data_path)
    with (
        patch.object(runner.get_settings(), 'mcmap_binary_path', str(fake)),
        pytest.raises(PlayerLocationExtractError, match='invalid JSON event'),
    ):
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
    fake = _write_fake_mcmap(payload, world_data_path)
    with (
        patch.object(runner.get_settings(), "mcmap_binary_path", str(fake)),
        patch_runtime_resource('docker_mc_manager', FakeDocker()),
    ):
        result = await world_restore.get_player_locations("srv1", _=_test_user())
    fake.unlink()
    assert result.players[0].region_dir_relpath == "world/region"


@pytest.mark.binary("mcmap")
async def test_real_player_nbt_preserves_positions_and_reports_invalid_files(world_data_path):
    import gzip
    import struct

    world = world_data_path / "world"
    modern = world / "playerdata"
    legacy = world / "players"
    modern.mkdir()
    legacy.mkdir()
    player_id = "0b4c4192-8eb3-4f0b-9022-8e2cb2ee6fc0"
    dimension = b"minecraft:overworld"
    modern_nbt = (
        b"\x0a\x00\x00"
        b"\x03\x00\x0bDataVersion" + struct.pack(">i", 3955)
        + b"\x09\x00\x03Pos\x06" + struct.pack(">i3d", 3, -10.5, 73.0, 20.25)
        + b"\x08\x00\x09Dimension" + struct.pack(">H", len(dimension)) + dimension
        + b"\x00"
    )
    legacy_nbt = (
        b"\x0a\x00\x00"
        b"\x09\x00\x03Pos\x06" + struct.pack(">i3d", 3, 1.0, 64.0, -2.0)
        + b"\x03\x00\x09Dimension" + struct.pack(">i", -1) + b"\x00"
    )
    (modern / f"{player_id}.dat").write_bytes(gzip.compress(modern_nbt))
    (legacy / "LegacyName.dat").write_bytes(legacy_nbt)
    damaged = modern / "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee.dat"
    damaged.write_bytes(b"not an NBT document")
    before = {path: path.read_bytes() for path in (*modern.iterdir(), *legacy.iterdir())}

    result = await extract_player_locations_for_server(world_data_path)

    players = {player.id: player for player in result.players}
    assert set(players) == {player_id, "LegacyName"}
    current = players[player_id]
    assert current.uuid == "0b4c41928eb34f0b90228e2cb2ee6fc0"
    assert current.region_dir_relpath == "world/region"
    assert (current.pos.x, current.pos.y, current.pos.z) == (-10.5, 73.0, 20.25)
    assert current.data_version == 3955
    old = players["LegacyName"]
    assert old.uuid is None and old.region_dir_relpath == "world/DIM-1/region"
    assert (old.pos.x, old.pos.y, old.pos.z) == (1.0, 64.0, -2.0)
    assert [(item.source, item.reason) for item in result.skipped] == [
        ("playerdata/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee.dat", "parse_error"),
    ]
    assert all(path.read_bytes() == content for path, content in before.items())
