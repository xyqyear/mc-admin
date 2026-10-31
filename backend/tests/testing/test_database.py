import asyncio

import pytest
from httpx2 import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.db.database import get_async_session
from app.main import app
from app.servers.models import Server
from app.templates.crud import get_template_by_id, save_template
from tests.support import database as database_support
from tests.support.database import database_at


async def test_request_commits_are_visible_to_background_work(database, isolated_runtime):
    headers = {"Authorization": f"Bearer {isolated_runtime.settings.master_token}"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", headers=headers) as client:
        response = await client.post("/api/templates/", json={
            "name": "shared-business-data", "description": "created by request",
            "yaml_template": 'services:\n  mc:\n    ports: ["25565:25565"]\n    environment: {SERVER_PORT: 25565}',
            "variable_definitions": [],
        })
        assert response.status_code == 201, response.text
        template_id = response.json()["id"]

        async def update_description():
            async with get_async_session() as session:
                template = await get_template_by_id(session, template_id)
                assert template is not None
                assert template.description == "created by request"
                template.description = "committed by background work"
                await save_template(session, template)

        await isolated_runtime.spawn(update_description(), name="test-template-update")
        response = await client.get(f"/api/templates/{template_id}")
        assert response.status_code == 200
        assert response.json()["description"] == "committed by background work"


async def test_failed_transaction_does_not_leak_or_poison_other_sessions(db_session_factory):
    async with db_session_factory() as writer:
        writer.add(Server(server_id="uncommitted"))
        await writer.flush()
        async with db_session_factory() as observer:
            assert list(await observer.scalars(select(Server))) == []
        await writer.rollback()

    async with db_session_factory() as writer:
        writer.add(Server(server_id="retained"))
        await writer.commit()

    async with db_session_factory() as writer:
        writer.add_all([Server(server_id="retained"), Server(server_id="must-rollback")])
        with pytest.raises(IntegrityError):
            await writer.commit()

    async with db_session_factory() as independent:
        independent.add(Server(server_id="after-failure"))
        await independent.commit()
    async with db_session_factory() as observer:
        assert set(await observer.scalars(select(Server.server_id))) == {"retained", "after-failure"}


async def test_cancelled_database_owner_releases_writer_and_preserves_commits(tmp_path):
    path = tmp_path / "cancelled.sqlite3"
    ready = asyncio.Event()

    async def own_database():
        async with database_at(path) as database, database.session_factory() as session:
            session.add(Server(server_id="committed"))
            await session.commit()
            session.add(Server(server_id="interrupted"))
            await session.flush()
            ready.set()
            await asyncio.Event().wait()

    owner = asyncio.create_task(own_database())
    try:
        await asyncio.wait_for(ready.wait(), timeout=5)
    finally:
        owner.cancel()
        with pytest.raises(asyncio.CancelledError):
            await owner

    async with database_at(path) as reopened:
        async with reopened.session_factory() as session:
            session.add(Server(server_id="reopened"))
            await session.commit()
        async with reopened.session_factory() as observer:
            assert set(await observer.scalars(select(Server.server_id))) == {"committed", "reopened"}


async def test_failed_database_initialization_closes_physical_connections(tmp_path, monkeypatch):
    path = tmp_path / "failed-setup.sqlite3"
    initialize = database_support.initialize_database
    drivers = []

    async def fail_after_creating_schema(database):
        await initialize(database)
        async with database.engine.connect() as connection:
            raw = await connection.get_raw_connection()
            drivers.append(raw.driver_connection)
        raise RuntimeError("fixture setup failed")

    with monkeypatch.context() as patch:
        patch.setattr(database_support, "initialize_database", fail_after_creating_schema)
        with pytest.raises(RuntimeError, match="fixture setup failed"):
            async with database_at(path):
                pytest.fail("A failed setup must not yield a database")

    assert drivers
    for driver in drivers:
        with pytest.raises(ValueError, match="no active connection"):
            await driver.execute("SELECT 1")
    async with database_at(path) as reopened:
        async with reopened.session_factory() as writer:
            writer.add(Server(server_id="after-setup-failure"))
            await writer.commit()
        async with reopened.session_factory() as reader:
            assert list(await reader.scalars(select(Server.server_id))) == ["after-setup-failure"]
