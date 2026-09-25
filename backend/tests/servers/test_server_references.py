from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.metadata import Base
from app.minecraft.instance import MCInstance
from app.servers.crud import create_server_record, mark_server_removed
from app.servers.references import resolve_server_ref, revalidate_server_ref


@pytest.fixture
async def sessions(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'identity.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


def server_directory(root: Path, name: str) -> Path:
    project = root / name
    (project / "data").mkdir(parents=True)
    (project / "compose.yaml").write_text("services: {}\n")
    return project


@pytest.mark.parametrize("name", ["Legacy.Server_01", "old server", "历史服务器", "back\\slash", "100%25"])
async def test_reference_preserves_safe_legacy_names(sessions, tmp_path, name):
    root = tmp_path / "identity-servers"
    project = server_directory(root, name)
    async with sessions() as session:
        row = await create_server_record(session, name)
        ref = await resolve_server_ref(session, name, servers_root=root)
        assert ref.server_id == name
        assert ref.generation == ref.server_db_id == ref.incarnation == row.id
        assert ref.project_path == project
        assert ref.data_path == project / "data"
        await revalidate_server_ref(session, ref)


@pytest.mark.parametrize("name", ["", ".", "..", "../other", "nested/server", "/absolute", "bad\x00name"])
def test_instance_rejects_unsafe_name_before_using_filesystem(tmp_path, name):
    with pytest.raises(HTTPException) as caught:
        MCInstance(tmp_path, name)
    assert caught.value.status_code == 400


async def test_existing_directory_never_implicitly_adopts(sessions, tmp_path):
    root = tmp_path / "identity-servers"
    server_directory(root, "unregistered")
    async with sessions() as session:
        with pytest.raises(HTTPException) as caught:
            await resolve_server_ref(session, "unregistered", servers_root=root)
        assert caught.value.status_code == 404
        assert "接管" in caught.value.detail
        row = await create_server_record(session, "unregistered")
        assert (await resolve_server_ref(session, "unregistered", servers_root=root)).generation == row.id


async def test_missing_and_deactivated_servers_are_distinct(sessions, tmp_path):
    root = tmp_path / "identity-servers"
    root.mkdir()
    async with sessions() as session:
        await create_server_record(session, "missing")
        with pytest.raises(HTTPException) as missing:
            await resolve_server_ref(session, "missing", servers_root=root)
        assert missing.value.status_code == 404
        ref = await resolve_server_ref(session, "missing", servers_root=root, require_exists=False)
        await mark_server_removed(session, "missing", datetime.now(UTC))
        with pytest.raises(HTTPException) as inactive:
            await resolve_server_ref(session, "missing", servers_root=root, require_exists=False)
        assert inactive.value.status_code == 409
        with pytest.raises(HTTPException) as stale:
            await revalidate_server_ref(session, ref, require_exists=False)
        assert stale.value.status_code == 409


async def test_recreated_name_invalidates_delayed_reference_even_with_cached_row(sessions, tmp_path):
    root = tmp_path / "identity-servers"
    server_directory(root, "survival")
    async with sessions() as delayed:
        first = await create_server_record(delayed, "survival")
        ref = await resolve_server_ref(delayed, "survival", servers_root=root)
        async with sessions() as replacement:
            await mark_server_removed(replacement, "survival", datetime.now(UTC))
            second = await create_server_record(replacement, "survival")
        assert second.id != first.id
        with pytest.raises(HTTPException) as stale:
            await revalidate_server_ref(delayed, ref)
        assert stale.value.status_code == 409
        assert "实例" in stale.value.detail


async def test_configured_root_symlink_is_supported(sessions, tmp_path):
    root = tmp_path / "identity-servers"
    project = server_directory(root, "survival")
    alias = tmp_path / "configured-root"
    alias.symlink_to(root, target_is_directory=True)
    async with sessions() as session:
        await create_server_record(session, "survival")
        ref = await resolve_server_ref(session, "survival", servers_root=alias)
    assert ref.servers_root == root
    assert ref.project_path == project


@pytest.mark.parametrize("target_inside_root", [False, True])
async def test_project_symlink_cannot_alias_another_server(sessions, tmp_path, target_inside_root):
    root = tmp_path / "identity-servers"
    root.mkdir()
    other = server_directory(root if target_inside_root else tmp_path, "other")
    (root / "survival").symlink_to(other, target_is_directory=True)
    async with sessions() as session:
        await create_server_record(session, "survival")
        with pytest.raises(HTTPException) as caught:
            await resolve_server_ref(session, "survival", servers_root=root)
        assert caught.value.status_code == 409
    with pytest.raises(HTTPException), patch("app.minecraft.instance.async_fs.rmtree", new_callable=AsyncMock) as remove:
        await MCInstance(root, "survival").remove()
    remove.assert_not_called()
    assert (other / "compose.yaml").exists()


async def test_data_symlink_escape_and_delayed_retarget_are_rejected(sessions, tmp_path):
    root = tmp_path / "identity-servers"
    project = server_directory(root, "survival")
    data = project / "data"
    data.rmdir()
    first = project / "storage-a"
    first.mkdir()
    second = project / "storage-b"
    second.mkdir()
    data.symlink_to(first, target_is_directory=True)
    async with sessions() as session:
        await create_server_record(session, "survival")
        ref = await resolve_server_ref(session, "survival", servers_root=root)
        assert ref.data_path == first
        data.unlink()
        data.symlink_to(second, target_is_directory=True)
        with pytest.raises(HTTPException) as changed:
            await revalidate_server_ref(session, ref)
        assert changed.value.status_code == 409
        data.unlink()
        data.symlink_to(tmp_path, target_is_directory=True)
        with pytest.raises(HTTPException):
            await MCInstance(root, "survival").exists()


async def test_compose_symlink_cannot_read_or_overwrite_other_project(tmp_path):
    root = tmp_path / "identity-servers"
    project = server_directory(root, "survival")
    secret = tmp_path / "outside.yaml"
    secret.write_text("synthetic-secret")
    compose = project / "compose.yaml"
    compose.unlink()
    compose.symlink_to(secret)
    with pytest.raises(HTTPException):
        await MCInstance(root, "survival").get_compose_file()
    assert secret.read_text() == "synthetic-secret"


async def test_server_properties_cannot_read_outside_data(tmp_path):
    root = tmp_path / "identity-servers"
    project = server_directory(root, "survival")
    secret = tmp_path / "outside.properties"
    secret.write_text("rcon.password=synthetic-secret")
    (project / "data/server.properties").symlink_to(secret)
    with pytest.raises(HTTPException):
        await MCInstance(root, "survival").get_server_properties()
