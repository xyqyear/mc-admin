"""Server discovery retains the database boundary when files drift."""

import logging
from datetime import UTC, datetime

import pytest

from app.auth.schemas import UserPublic
from app.routers.servers.misc import get_server, get_servers
from app.servers.models import Server
from tests.fixtures.test_utils import create_mc_server_compose_yaml


@pytest.fixture
def owner():
    return UserPublic(id=1, username="owner", created_at=datetime.now(UTC))


async def test_get_servers_filters_drifted_row_and_logs(database, isolated_runtime, owner, caplog):
    manager = isolated_runtime.docker_mc_manager
    await manager.get_instance("good").create(create_mc_server_compose_yaml("good", 25565, 25575))
    async with database.session_factory() as session:
        session.add_all([Server(server_id="good"), Server(server_id="drifted")])
        await session.commit()
    with caplog.at_level(logging.WARNING):
        async with database.session_factory() as session:
            result = await get_servers(db=session, _=owner)

    assert [server.id for server in result] == ["good"]
    assert any("drifted" in record.message and "cannot read compose" in record.message for record in caplog.records)


async def test_get_servers_empty_when_no_active_rows(database, isolated_runtime, owner):
    await isolated_runtime.docker_mc_manager.get_instance("orphan").create(
        create_mc_server_compose_yaml("orphan", 25565, 25575),
    )
    async with database.session_factory() as session:
        result = await get_servers(db=session, _=owner)
    assert result == []


@pytest.mark.parametrize("generation", [42, None])
async def test_server_detail_exposes_current_generation_without_hiding_unregistered_data(
    database, isolated_runtime, owner, generation,
):
    await isolated_runtime.docker_mc_manager.get_instance("survival").create(
        create_mc_server_compose_yaml("survival", 25565, 25575),
    )
    if generation is not None:
        async with database.session_factory() as session:
            session.add(Server(id=generation, server_id="survival"))
            await session.commit()
    async with database.session_factory() as session:
        result = await get_server("survival", db=session, _=owner)
    assert result.id == "survival"
    assert result.server_generation == generation
    assert result.gamePort == 25565
