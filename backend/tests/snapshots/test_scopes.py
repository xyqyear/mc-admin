import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.metadata import Base
from app.operations.coordinator import ResourceClaim, ResourceKind
from app.servers.models import Server
from app.snapshots.scopes import (
    GlobalScope,
    PathsScope,
    ServerScope,
    WorldScope,
    resolve_scope,
    scope_adapter,
)


@pytest.fixture
async def scope_case(tmp_path):
    root = tmp_path / "servers"
    project = root / "survival"
    data = project / "data"
    (data / "plugins" / "example").mkdir(parents=True)
    (project / "compose.yaml").write_text("services: {}\n")
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'scope.sqlite3'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions() as session:
        session.add(Server(server_id="survival"))
        await session.commit()
    try:
        yield root, data, sessions
    finally:
        await engine.dispose()


async def test_global_project_and_data_scopes_preserve_distinct_meanings(scope_case):
    root, data, sessions = scope_case
    results = [
        await resolve_scope(scope, root=root, sessions=sessions)
        for scope in (
            GlobalScope(),
            ServerScope(server_id="survival"),
            PathsScope(server_id="survival", paths=(".",)),
        )
    ]
    assert [result.paths for result in results] == [(root,), (data.parent,), (data,)]
    assert results[0].claims == (ResourceClaim(ResourceKind.FILES),)
    assert all(
        result.servers[0].generation == results[0].servers[0].generation
        for result in results
    )


async def test_global_scope_keeps_unregistered_content_without_inventing_identity(
    scope_case,
):
    root, data, sessions = scope_case
    unregistered = root / "imported" / "data"
    unregistered.mkdir(parents=True)
    (unregistered.parent / "compose.yaml").write_text("services: {}\n")
    (unregistered / "retained.txt").write_text("unregistered content")
    (data.parent / "compose.yaml").unlink()
    result = await resolve_scope(GlobalScope(), root=root, sessions=sessions)
    assert result.paths == (root,)
    assert [reference.server_id for reference in result.servers] == ["survival"]
    assert unregistered.is_relative_to(result.paths[0])
    assert result.claims == (ResourceClaim(ResourceKind.FILES),)


async def test_nested_paths_are_restored_once_and_alias_claims_are_retained(scope_case):
    root, data, sessions = scope_case
    (data / "alias").symlink_to(data / "plugins", target_is_directory=True)
    scope = PathsScope(
        server_id="survival", paths=("plugins/example", "plugins", "alias", "plugins")
    )
    result = await resolve_scope(scope, root=root, sessions=sessions)
    assert result.paths == (data / "plugins",)
    assert ResourceClaim(ResourceKind.FILES, "survival", "data/alias") in result.claims
    assert (
        ResourceClaim(ResourceKind.FILES, "survival", "data/plugins") in result.claims
    )


async def test_symlink_cannot_escape_data_scope_into_project(scope_case):
    root, data, sessions = scope_case
    (data / "compose-link").symlink_to(data.parent / "compose.yaml")
    with pytest.raises(HTTPException) as caught:
        await resolve_scope(
            PathsScope(server_id="survival", paths=("compose-link",)),
            root=root,
            sessions=sessions,
        )
    assert caught.value.status_code == 400
    assert (data.parent / "compose.yaml").read_text() == "services: {}\n"


@pytest.mark.parametrize(
    "paths", [[], ["../compose.yaml"], ["/etc/passwd"], ["a/../../b"], [""]]
)
def test_invalid_path_selection_is_rejected(paths):
    with pytest.raises(ValidationError):
        scope_adapter.validate_python(
            {"kind": "paths", "server_id": "survival", "paths": paths}
        )


@pytest.mark.parametrize(
    "selection",
    [
        {"type": "regions", "region_dir_relpath": "world/region", "regions": []},
        {"type": "chunks", "region_dir_relpath": "world/region", "chunks": []},
        {"type": "world", "region_dir_relpath": "world/region"},
        {"type": "dimension", "region_dir_relpath": "../region"},
        {"type": "dimension", "region_dir_relpath": "world/entities"},
        {"type": "paths"},
    ],
)
def test_empty_or_ambiguous_world_scope_is_rejected(selection):
    with pytest.raises(ValidationError):
        scope_adapter.validate_python(
            {"kind": "world", "server_id": "survival", "selection": selection}
        )


def test_negative_chunks_survive_scope_roundtrip_without_duplicate_work():
    scope = scope_adapter.validate_python(
        {
            "kind": "world",
            "server_id": "survival",
            "selection": {
                "type": "chunks",
                "region_dir_relpath": "world/region",
                "chunks": [[-1, 32], [-1, 32], [0, 0]],
            },
        }
    )
    assert isinstance(scope, WorldScope)
    assert scope.selection.chunks == [(-1, 32), (0, 0)]
    assert scope_adapter.validate_json(scope_adapter.dump_json(scope)) == scope
