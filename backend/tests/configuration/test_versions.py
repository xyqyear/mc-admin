import asyncio
from contextlib import aclosing

import pytest
from httpx2 import ASGITransport, AsyncClient

from app.configuration import application
from app.main import create_app
from app.servers.models import Server, ServerStatus
from app.templates import StringVariableDefinition
from app.templates.models import serialize_variable_definitions
from app.templates.tables import ServerTemplate

from .conftest import COMPOSE


@pytest.fixture
async def client(configuration):
    configuration.runtime.settings.master_token = "synthetic-configuration-token"
    app = create_app(runtime=configuration.runtime)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", headers={"Authorization": "Bearer synthetic-configuration-token"}) as client:
        yield client


@pytest.fixture
async def template(configuration):
    async with configuration.journal.session_factory() as db:
        row = ServerTemplate(
            name="legacy snapshot source", yaml_template=COMPOSE.replace('MEMORY: "2G"', 'MEMORY: "{memory}"'),
            variable_definitions_json=serialize_variable_definitions([
                StringVariableDefinition(name="memory", display_name="内存", default="2G"),
            ]),
        )
        db.add(row)
        await db.commit()
        return row.id


async def await_submission(configuration, response):
    assert response.status_code == 200, response.text
    future = configuration.tasks.get_future(response.json()["task_id"])
    assert future is not None
    return await asyncio.wait_for(future, 5)


async def test_versioned_save_conflict_and_legacy_last_write(configuration, client):
    observed = (await client.get("/api/servers/first/compose")).json()
    new_content = COMPOSE.replace('MEMORY: "2G"', 'MEMORY: "3G"')
    accepted = await client.post("/api/servers/first/compose", json={"yaml_content": new_content, "expected_version": observed["version"]})
    assert (await await_submission(configuration, accepted)).success
    stale = await client.post("/api/servers/first/compose", json={"yaml_content": COMPOSE, "expected_version": observed["version"]})
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "configuration_conflict"
    assert stale.json()["detail"]["current_version"] == (await configuration.state()).version
    assert configuration.compose.read_text() == new_content
    legacy = await client.post("/api/servers/first/compose", json={"yaml_content": COMPOSE})
    assert (await await_submission(configuration, legacy)).success
    assert configuration.compose.read_text() == COMPOSE
    configuration.up.assert_not_awaited()


async def test_external_file_edits_are_checked_on_every_read_and_before_save(configuration, client):
    observed = (await client.get("/api/servers/first/compose")).json()
    configuration.compose.write_text(COMPOSE + "# 外部编辑\n")
    current = (await client.get("/api/servers/first/compose")).json()
    assert current["version"] != observed["version"] and "外部编辑" in current["yaml_content"]
    stale = await client.post("/api/servers/first/compose", json={"yaml_content": COMPOSE, "expected_version": observed["version"]})
    assert stale.status_code == 409
    assert not configuration.tasks.get_all_tasks()
    accepted = await client.post("/api/servers/first/compose", json={"yaml_content": COMPOSE, "expected_version": current["version"]})
    assert (await await_submission(configuration, accepted)).success


async def test_accepted_task_rechecks_version_and_retains_conflict_across_history_restore(configuration, client, monkeypatch):
    entered, release = asyncio.Event(), asyncio.Event()
    original = application._rebuild_server

    async def delayed(server_id, prepared):
        entered.set()
        await release.wait()
        async with aclosing(original(server_id, prepared)) as events:
            async for event in events:
                yield event

    monkeypatch.setattr(application, "_rebuild_server", delayed)
    observed = (await client.get("/api/servers/first/compose")).json()
    accepted = await client.post("/api/servers/first/compose", json={"yaml_content": COMPOSE, "expected_version": observed["version"]})
    try:
        await asyncio.wait_for(entered.wait(), 3)
        configuration.compose.write_text(COMPOSE + "# after acceptance\n")
    finally:
        release.set()
    assert not (await await_submission(configuration, accepted)).success
    task_id = accepted.json()["task_id"]
    task = (await client.get(f"/api/tasks/{task_id}")).json()
    assert task["error_code"] == "configuration_conflict"
    assert task["status"] == "failed"
    record = await configuration.journal.get(task_id)
    assert record is not None and record.failure_code == "configuration_conflict" and not record.data_changed
    configuration.tasks.restore_history([record])
    restored = (await client.get(f"/api/tasks/{task_id}")).json()
    assert restored["error_code"] == "configuration_conflict"
    configuration.down.assert_not_awaited()
    configuration.up.assert_not_awaited()


async def test_mode_conversions_share_version_and_preserve_legacy_no_body(configuration, client, template):
    original = (await client.get("/api/servers/first/compose")).json()
    extraction = await client.post("/api/servers/first/extract-variables", json={"template_id": template})
    comparison = await client.post("/api/servers/first/check-conversion", json={"template_id": template, "variable_values": {"memory": "2G"}})
    assert extraction.json()["version"] == comparison.json()["version"] == original["version"]
    converted = await client.post("/api/servers/first/convert-to-template", json={"template_id": template, "variable_values": {}, "expected_version": original["version"]})
    assert converted.status_code == 200, converted.text
    assert converted.json() == {"task_id": None, "skipped_rebuild": True}
    source = (await client.get("/api/servers/first/template-config")).json()
    assert source["version"] != original["version"]
    assert source["version"] == (await client.get("/api/servers/first/compose")).json()["version"]
    assert source["variable_values"] == {"memory": "2G"}
    stale = await client.post("/api/servers/first/convert-to-direct", json={"expected_version": original["version"]})
    assert stale.status_code == 409
    legacy = await client.post("/api/servers/first/convert-to-direct")
    assert legacy.status_code == 200 and legacy.json()["success"]
    assert (await configuration.state()).template_id is None
    assert configuration.compose.read_text() == COMPOSE
    configuration.down.assert_not_awaited()
    configuration.up.assert_not_awaited()


async def test_snapshot_update_uses_captured_source_and_rejects_stale_version(configuration, client, template):
    response = await client.post("/api/servers/first/convert-to-template", json={"template_id": template, "variable_values": {"memory": "2G"}})
    assert response.status_code == 200
    source = (await client.get("/api/servers/first/template-config")).json()
    async with configuration.journal.session_factory() as db:
        row = await db.get(ServerTemplate, template)
        assert row is not None
        row.yaml_template = "source changed entirely"
        await db.commit()
    accepted = await client.put("/api/servers/first/template-config", json={"variable_values": {"memory": "3G"}, "expected_version": source["version"]})
    assert (await await_submission(configuration, accepted)).success
    current = (await client.get("/api/servers/first/template-config")).json()
    assert current["yaml_template"] == source["yaml_template"]
    assert current["variable_values"] == {"memory": "3G"}
    assert 'MEMORY: "3G"' in configuration.compose.read_text()
    stale = await client.put("/api/servers/first/template-config", json={"variable_values": {"memory": "4G"}, "expected_version": source["version"]})
    assert stale.status_code == 409
    legacy = await client.put("/api/servers/first/template-config", json={"variable_values": {"memory": "4G"}})
    assert (await await_submission(configuration, legacy)).success
    configuration.up.assert_not_awaited()


async def test_identical_files_from_recreated_server_have_different_versions(configuration, client):
    observed = (await configuration.state()).version
    async with configuration.journal.session_factory() as db:
        row = await db.get(Server, 1)
        assert row is not None
        row.status = ServerStatus.REMOVED
        await db.flush()
        db.add(Server(server_id="first"))
        await db.commit()
    assert (await configuration.state()).version != observed
    stale = await client.post("/api/servers/first/compose", json={"yaml_content": COMPOSE, "expected_version": observed})
    assert stale.status_code == 409
    assert configuration.compose.read_text() == COMPOSE
