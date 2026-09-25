from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from httpx2 import ASGITransport, AsyncClient

from app.auth.models import User, UserRole
from app.auth.schemas import UserPublic
from app.auth.service import get_identity_service
from app.auth.session import AUTH_COOKIE_NAME, CSRF_COOKIE_NAME, CSRF_HEADER_NAME
from app.db.metadata import Base
from app.main import create_app
from app.operations.journal_types import (
    OperationSpec,
    OperationState,
    ProcessIdentity,
    RecoveryReference,
    ResourceReference,
)
from app.operations.recovery import RecoveryService


@pytest.fixture
async def operation_client(journal, isolated_runtime):
    async with isolated_runtime.database.engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    isolated_runtime.journal = journal
    recovery = RecoveryService(journal, probe=AsyncMock(return_value=False), validate_resource=AsyncMock(return_value=True))
    isolated_runtime.resources["operation_recovery"] = recovery
    await journal.accept(OperationSpec("world_restore", (ResourceReference("world", "survival", 12),), operation_id="retained", actor_id=41))
    await journal.start("retained")
    await journal.register_process("retained", ProcessIdentity(123, 123, 456, "synthetic-boot", 12, 34))
    await journal.finish("retained", OperationState.INTERRUPTED, writers_stopped=False,
                         recovery_refs=[RecoveryReference("snapshot", "a" * 64)])
    app = create_app(runtime=isolated_runtime)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client, recovery
    await journal.resolve("retained", actor_id=0, writers_stopped=True)
    await isolated_runtime.close()


async def sign_in(client, role: UserRole, runtime) -> str:
    created_at = datetime.now(UTC)
    async with runtime.database.session_factory() as session:
        session.add(User(id=41, username="synthetic-user", hashed_password="unused", role=role, created_at=created_at))
        await session.commit()
    token, csrf = get_identity_service().create_session_token(UserPublic(id=41, username="synthetic-user", role=role, created_at=created_at))
    client.cookies.set(AUTH_COOKIE_NAME, token)
    client.cookies.set(CSRF_COOKIE_NAME, csrf)
    return csrf


async def test_operation_history_requires_authentication(operation_client):
    client, _ = operation_client
    assert (await client.get("/api/operations")).status_code == 401
    assert (await client.get("/api/operations/retained")).status_code == 401
    assert (await client.post("/api/operations/retained/resolve", json={"action": "acknowledge_partial"})).status_code == 401


async def test_admin_reads_history_but_cannot_release_recovery(operation_client, isolated_runtime):
    client, _ = operation_client
    csrf = await sign_in(client, UserRole.ADMIN, isolated_runtime)
    response = await client.get("/api/operations")
    assert response.status_code == 200
    assert response.json()[0]["state"] == "interrupted"
    assert response.json()[0]["resources"][0]["generation"] == 12
    assert "processes" not in response.text and "root_ino" not in response.text
    assert (await client.post("/api/operations/retained/resolve", json={"action": "acknowledge_partial"}, headers={CSRF_HEADER_NAME: csrf})).status_code == 403


async def test_owner_requires_csrf_and_confirmed_writers_with_no_force_bypass(operation_client, isolated_runtime):
    client, recovery = operation_client
    csrf = await sign_in(client, UserRole.OWNER, isolated_runtime)
    path = "/api/operations/retained/resolve"
    assert (await client.post(path, json={"action": "acknowledge_partial"})).status_code == 403
    headers = {CSRF_HEADER_NAME: csrf}
    assert (await client.post(path, json={"action": "acknowledge_partial", "force": True}, headers=headers)).status_code == 422
    assert (await client.post(path, json={"action": "acknowledge_partial"}, headers=headers)).status_code == 409
    recovery.probe = AsyncMock(return_value=True)
    response = await client.post(path, json={"action": "acknowledge_partial"}, headers=headers)
    assert response.status_code == 200
    assert response.json()["resolved_by"] == 41
    assert response.json()["resolved_at"] is not None
    assert response.json()["recovery_reason"] is None
    assert response.json()["writers_stopped"] is True
    assert response.json()["recovery_refs"][0]["resolved"] is False
    released = await client.post(path, json={"action": "acknowledge_partial", "resolve_references": True}, headers=headers)
    assert released.status_code == 200
    assert released.json()["recovery_refs"][0]["resolved"] is True
