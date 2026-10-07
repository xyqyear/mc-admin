import zlib
from pathlib import Path

import pytest

import app.world.scope_execution as chunk_execution
from app.dynamic_config.configs.mcmap import MCMapConfig
from app.mcmap.types import MCMapError
from app.runtime_resources import current_runtime
from app.snapshots.restoration_models import RestorationType
from app.snapshots.scopes import PathsScope, WorldScope
from app.snapshots.selection_models import RestorationSelection
from app.world.artifacts import artifact_root
from app.world.scope_execution import RestoreScopeExecutor
from tests.support.regions import chunk_value, region_bytes

from .support import complete

pytestmark = [
    pytest.mark.binary("restic"),
    pytest.mark.binary("fd"),
    pytest.mark.binary("mcmap"),
]


def selected_scope(kind, world_name):
    return WorldScope(
        server_id="survival",
        selection=RestorationSelection(
            type=RestorationType(kind),
            region_dir_relpath=f"{world_name}/region",
            regions=[(0, 0)] if kind == "regions" else [],
            chunks=[(0, 0)] if kind == "chunks" else [],
        ),
    )


@pytest.mark.parametrize("kind", ["dimension", "regions", "chunks"])
@pytest.mark.parametrize(
    ("ignored_name", "selected_name"),
    [("world", "world_alias"), ("world_alias", "world")],
)
async def test_world_restore_uses_its_selected_name_and_retains_rollback(
    world_case, kind, ignored_name, selected_name,
):
    case = world_case
    alias = case.data / "world_alias"
    alias.symlink_to(case.region.parent, target_is_directory=True)
    files = [case.region / "r.0.0.mca"]
    for sub in ("entities", "poi"):
        directory = case.region.parent / sub
        directory.mkdir()
        path = directory / "r.0.0.mca"
        path.write_bytes(region_bytes([f"source {sub} zero", f"source {sub} one"]))
        files.append(path)
    source_values = [(chunk_value(path, 0), chunk_value(path, 1)) for path in files]
    case.config.snapshots.ignored_paths = [ignored_name]
    selected = selected_scope(kind, selected_name)
    target = await case.commands.check_world_target(selected)
    assert target.allowed
    source = await complete(
        case, await case.commands.create(selected_scope("dimension", selected_name), 1)
    )
    for path in files:
        path.write_bytes(region_bytes(["live zero", "live one"]))

    accepted = await case.commands.restore(selected, source["snapshot"]["id"], 1)
    await complete(case, accepted)

    for path, (source_zero, source_one) in zip(files, source_values, strict=True):
        assert chunk_value(path, 0) == source_zero
        assert chunk_value(path, 1) == ("live one" if kind == "chunks" else source_one)
    assert alias.is_symlink()
    await complete(case, await case.commands.rollback(accepted["restoration_id"], 1))
    for path in files:
        assert chunk_value(path, 0) == "live zero"
        assert chunk_value(path, 1) == "live one"
    assert alias.is_symlink()


@pytest.mark.parametrize("ignored_name", ["world", "world_alias"])
async def test_alias_chunk_restore_keeps_only_logically_excluded_mcc_entries(
    world_case, ignored_name,
):
    case = world_case
    alias = case.data / "world_alias"
    alias.symlink_to(case.region.parent, target_is_directory=True)
    selected = WorldScope(
        server_id="survival",
        selection=RestorationSelection(
            type=RestorationType.CHUNKS,
            region_dir_relpath="world_alias/region",
            chunks=[(0, 0), (1, 0)],
        ),
    )
    source = await complete(
        case, await case.commands.create(selected_scope("dimension", "world_alias"), 1)
    )
    mca = case.region / "r.0.0.mca"
    mca.write_bytes(region_bytes(["live zero", "live one"]))
    case.config.snapshots.ignored_paths = [f"{ignored_name}/region/c.0.0.mcc"]

    accepted = await case.commands.restore(selected, source["snapshot"]["id"], 1)
    await complete(case, accepted)

    assert chunk_value(mca, 0) == (
        "live zero" if ignored_name == "world_alias" else "source zero"
    )
    assert chunk_value(mca, 1) == "source one"
    await complete(case, await case.commands.rollback(accepted["restoration_id"], 1))
    assert chunk_value(mca, 0) == "live zero"
    assert chunk_value(mca, 1) == "live one"
    assert alias.is_symlink()


@pytest.mark.parametrize("kind", ["regions", "chunks"])
@pytest.mark.parametrize("ignored_name", ["world", "world_alias"])
async def test_alias_map_preview_uses_logical_mcc_rules_and_preserves_live_data(
    world_case, kind, ignored_name,
):
    case = world_case
    case.config.mcmap = MCMapConfig()
    (case.data / "world_alias").symlink_to(
        case.region.parent, target_is_directory=True
    )
    header = bytearray(8192)
    for chunk in range(3):
        header[chunk * 4 : chunk * 4 + 4] = ((chunk + 2) << 8 | 1).to_bytes(4)
    mca = case.region / "r.0.0.mca"
    mca.write_bytes(bytes(header) + b"\x00\x00\x00\x01\x82".ljust(4096, b"\0") * 3)
    for chunk in range(3):
        (case.region / f"c.{chunk}.0.mcc").write_bytes(
            zlib.compress(f"source {chunk}".encode())
        )
    selected = WorldScope(
        server_id="survival",
        selection=RestorationSelection(
            type=RestorationType(kind),
            region_dir_relpath="world_alias/region",
            regions=[(0, 0)] if kind == "regions" else [],
            chunks=[(0, 0), (1, 0)] if kind == "chunks" else [],
        ),
    )
    source = await complete(
        case, await case.commands.create(selected_scope("dimension", "world_alias"), 1)
    )
    for chunk in range(3):
        (case.region / f"c.{chunk}.0.mcc").write_bytes(
            zlib.compress(f"live {chunk}".encode())
        )
    live_mca = mca.read_bytes()
    case.config.snapshots.ignored_paths = [
        ".mcmap", f"{ignored_name}/region/c.0.0.mcc"
    ]
    cache = case.data / ".mcmap"
    cache.mkdir()
    (cache / "palette.json").write_text("{}")
    previews = current_runtime().snapshot_previews
    assert previews is not None

    result = await complete(
        case, await previews.submit(selected, source["snapshot"]["id"], 1)
    )

    directory = previews.manager.get_session_dir(result["preview_id"])
    assert directory is not None
    staged = case.snapshots.stage_destination(
        directory / ("preview" if kind == "chunks" else "source"), case.region
    )
    assert zlib.decompress((staged / "c.0.0.mcc").read_bytes()) == (
        b"live 0" if ignored_name == "world_alias" else b"source 0"
    )
    assert zlib.decompress((staged / "c.1.0.mcc").read_bytes()) == b"source 1"
    assert zlib.decompress((staged / "c.2.0.mcc").read_bytes()) == (
        b"live 2" if kind == "chunks" else b"source 2"
    )
    assert mca.read_bytes() == live_mca
    for chunk in range(3):
        assert zlib.decompress((case.region / f"c.{chunk}.0.mcc").read_bytes()) == (
            f"live {chunk}".encode()
        )
    await complete(case, await previews.end(result["preview_id"], 1))
    assert not directory.exists()


def linked_external_region(case, linked_kind):
    mca = case.region / "r.0.0.mca"
    header = bytearray(8192)
    for chunk in range(3):
        header[chunk * 4 : chunk * 4 + 4] = ((chunk + 2) << 8 | 1).to_bytes(4)
    mca.write_bytes(bytes(header) + b"\x00\x00\x00\x01\x82".ljust(4096, b"\0") * 3)
    paths = [mca]
    for chunk in range(3):
        path = case.region / f"c.{chunk}.0.mcc"
        path.write_bytes(zlib.compress(f"source {chunk}".encode()))
        paths.append(path)
    (case.region / "r.1.0.mca").write_bytes(region_bytes(["other region"]))
    shared = case.data / "shared"
    shared.mkdir()
    link = paths[0 if linked_kind == "mca" else 1]
    actual = shared / ("terrain.mca" if linked_kind == "mca" else "overflow.mcc")
    link.rename(actual)
    link.symlink_to(actual)
    return paths, link, actual


def file_scope(case, paths):
    return PathsScope(
        server_id="survival",
        paths=tuple(path.relative_to(case.data).as_posix() for path in paths),
    )


def two_chunks():
    return WorldScope(
        server_id="survival",
        selection=RestorationSelection(
            type=RestorationType.CHUNKS,
            region_dir_relpath="world/region",
            chunks=[(0, 0), (1, 0)],
        ),
    )


@pytest.mark.parametrize("linked_kind", ["mca", "mcc"])
async def test_file_level_world_links_restore_actual_files_with_logical_sidecars(
    world_case, linked_kind,
):
    case = world_case
    paths, link, actual = linked_external_region(case, linked_kind)
    case.config.snapshots.ignored_paths = ["shared"]
    source = await complete(case, await case.commands.create(file_scope(case, paths), 1))
    for chunk, path in enumerate(paths[1:]):
        path.write_bytes(zlib.compress(f"live {chunk}".encode()))

    accepted = await case.commands.restore(two_chunks(), source["snapshot"]["id"], 1)
    await complete(case, accepted)

    assert link.is_symlink()
    assert link.resolve() == actual
    assert [zlib.decompress(path.read_bytes()) for path in paths[1:]] == [
        b"source 0", b"source 1", b"live 2"
    ]
    assert chunk_value(case.region / "r.1.0.mca", 0) == "other region"
    await complete(case, await case.commands.rollback(accepted["restoration_id"], 1))
    assert link.is_symlink()
    assert [zlib.decompress(path.read_bytes()) for path in paths[1:]] == [
        b"live 0", b"live 1", b"live 2"
    ]
    assert not current_runtime().world_restore_stages
    assert not list(case.data.rglob(".mc-admin-chunk-*"))


@pytest.mark.parametrize("failure_phase", ["merge", "publish"])
async def test_linked_chunk_failure_retains_live_mca_and_cleans_owned_artifacts(
    world_case, monkeypatch, failure_phase,
):
    case = world_case
    paths, link, actual = linked_external_region(case, "mca")
    source = await complete(case, await case.commands.create(file_scope(case, paths), 1))
    for chunk, path in enumerate(paths[1:]):
        path.write_bytes(zlib.compress(f"live {chunk}".encode()))
    live_mca = actual.read_bytes()
    original_replace = chunk_execution.aioos.replace

    async def fail_merge(self, **kwargs):
        raise MCMapError("合并失败")

    async def fail_publish(source, target):
        if Path(target) == actual:
            raise OSError("owned publication failure")
        await original_replace(source, target)

    with monkeypatch.context() as context:
        if failure_phase == "merge":
            context.setattr(RestoreScopeExecutor, "replace_selected_chunks", fail_merge)
        else:
            context.setattr(chunk_execution.aioos, "replace", fail_publish)
        accepted = await case.commands.restore(two_chunks(), source["snapshot"]["id"], 1)
        await complete(case, accepted, success=False)

    assert link.is_symlink()
    assert actual.read_bytes() == live_mca
    if failure_phase == "merge":
        assert [zlib.decompress(path.read_bytes()) for path in paths[1:]] == [
            b"live 0", b"live 1", b"live 2"
        ]
    assert not current_runtime().world_restore_stages
    assert not list(artifact_root("restore-stage").iterdir())
    assert not list(case.data.rglob(".mc-admin-chunk-*"))
    await complete(case, await case.commands.rollback(accepted["restoration_id"], 1))
    assert link.is_symlink()
    assert [zlib.decompress(path.read_bytes()) for path in paths[1:]] == [
        b"live 0", b"live 1", b"live 2"
    ]


@pytest.mark.parametrize("kind", ["regions", "chunks"])
@pytest.mark.parametrize("linked_kind", ["mca", "mcc"])
async def test_file_level_world_preview_groups_mca_and_mcc_without_live_writes(
    world_case, kind, linked_kind,
):
    case = world_case
    case.config.mcmap = MCMapConfig()
    paths, link, actual = linked_external_region(case, linked_kind)
    source = await complete(case, await case.commands.create(file_scope(case, paths), 1))
    for chunk, path in enumerate(paths[1:]):
        path.write_bytes(zlib.compress(f"live {chunk}".encode()))
    live_mca = paths[0].read_bytes()
    cache = case.data / ".mcmap"
    cache.mkdir()
    (cache / "palette.json").write_text("{}")
    selected = two_chunks() if kind == "chunks" else selected_scope(kind, "world")
    previews = current_runtime().snapshot_previews
    assert previews is not None

    result = await complete(
        case, await previews.submit(selected, source["snapshot"]["id"], 1)
    )

    directory = previews.manager.get_session_dir(result["preview_id"])
    assert directory is not None
    staged = case.snapshots.stage_destination(
        directory / ("preview" if kind == "chunks" else "source"), case.region
    )
    assert (staged / "r.0.0.mca").is_file()
    assert [
        zlib.decompress((staged / f"c.{chunk}.0.mcc").read_bytes())
        for chunk in range(3)
    ] == [b"source 0", b"source 1", b"live 2" if kind == "chunks" else b"source 2"]
    session = previews.manager.get_session(result["preview_id"])
    assert session is not None and session.affected_keys == {(0, 0)}
    assert link.is_symlink() and link.resolve() == actual
    assert paths[0].read_bytes() == live_mca
    assert [zlib.decompress(path.read_bytes()) for path in paths[1:]] == [
        b"live 0", b"live 1", b"live 2"
    ]
    await complete(case, await previews.end(result["preview_id"], 1))
    assert not directory.exists()


async def test_link_changes_after_chunk_merge_reject_every_live_publication(
    world_case, monkeypatch,
):
    case = world_case
    paths, link, actual = linked_external_region(case, "mca")
    source = await complete(case, await case.commands.create(file_scope(case, paths), 1))
    for chunk, path in enumerate(paths[1:]):
        path.write_bytes(zlib.compress(f"live {chunk}".encode()))
    live_mca = actual.read_bytes()
    original_merge = RestoreScopeExecutor.replace_selected_chunks
    redirected = actual.parent / "redirected.mcc"

    async def redirect_after_merge(self, **kwargs):
        await original_merge(self, **kwargs)
        paths[2].rename(redirected)
        paths[2].symlink_to(redirected)

    monkeypatch.setattr(
        RestoreScopeExecutor, "replace_selected_chunks", redirect_after_merge
    )

    accepted = await case.commands.restore(two_chunks(), source["snapshot"]["id"], 1)
    await complete(case, accepted, success=False)

    assert link.is_symlink()
    assert actual.read_bytes() == live_mca
    assert [zlib.decompress(path.read_bytes()) for path in paths[1:]] == [
        b"live 0", b"live 1", b"live 2"
    ]
    assert not current_runtime().world_restore_stages
    assert not list(case.data.rglob(".mc-admin-chunk-*"))
