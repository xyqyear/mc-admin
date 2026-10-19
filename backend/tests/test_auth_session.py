from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth.models import User, UserRole
from app.auth.session import AUTH_COOKIE_NAME, CSRF_COOKIE_NAME, CSRF_HEADER_NAME
from app.auth.store import delete_user
from app.config import get_settings
from app.main import app
from tests.support.auth import PASSWORD, create_account, login


@pytest.fixture
async def user(db_session_factory):
    return await create_account(db_session_factory)


@pytest.fixture
def client(database):
    client = TestClient(app, raise_server_exceptions=False)
    try:
        yield client
    finally:
        client.close()


def _set_cookie_header(headers: list[str], name: str) -> str:
    return next(header for header in headers if header.startswith(f"{name}="))


def test_password_login_sets_auth_cookies_and_authenticates_current_user(client, user):
    response = login(client, user.username)
    assert response.json()["user"]["username"] == user.username
    assert "access_token" not in response.json()
    assert "token_type" not in response.json()
    headers = response.headers.get_list("set-cookie")
    session = _set_cookie_header(headers, AUTH_COOKIE_NAME)
    csrf = _set_cookie_header(headers, CSRF_COOKIE_NAME)
    assert "HttpOnly" in session and "Path=/api" in session
    assert "HttpOnly" not in csrf and "Path=/" in csrf
    current = client.get("/api/user/me")
    assert current.status_code == 200
    assert current.json()["id"] == user.id
    assert current.json()["role"] == "owner"
    assert "hashed_password" not in current.json()


@pytest.mark.parametrize("username,password", [("owner", "wrong"), ("missing", PASSWORD)])
def test_invalid_credentials_cannot_establish_session(client, user, username, password):
    response = client.post("/api/auth/token", data={"username": username, "password": password})
    assert response.status_code == 401
    assert AUTH_COOKIE_NAME not in client.cookies
    assert client.get("/api/user/me").status_code == 401


def test_current_user_requires_authentication(client):
    assert client.get("/api/user/me").status_code == 401


def test_master_token_takes_precedence_over_stale_session_cookie(client):
    client.cookies.set(AUTH_COOKIE_NAME, "stale-session", path="/api")
    response = client.get("/api/user/me", headers={"Authorization": f"Bearer {get_settings().master_token}"})
    assert response.status_code == 200
    assert response.json()["username"] == "SYSTEM"


@pytest.mark.parametrize("csrf", [None, "wrong-token", "matching"])
async def test_cookie_mutation_requires_matching_csrf_before_persisting_user(client, user, db_session_factory, csrf):
    login(client, user.username)
    if csrf is None:
        del client.headers[CSRF_HEADER_NAME]
    elif csrf != "matching":
        client.headers[CSRF_HEADER_NAME] = csrf
    response = client.post("/api/admin/users", json={"username": "new-admin", "password": PASSWORD, "role": "admin"})
    assert response.status_code == (200 if csrf == "matching" else 403), response.text
    async with db_session_factory() as session:
        created = await session.scalar(select(User).where(User.username == "new-admin"))
        assert (created is not None) == (csrf == "matching")
        if created is not None:
            assert created.role == UserRole.ADMIN
            assert created.hashed_password != PASSWORD


def test_logout_clears_cookies_and_prevents_subsequent_authenticated_request(client, user):
    login(client, user.username)
    response = client.post("/api/auth/logout")
    assert response.status_code == 204
    headers = response.headers.get_list("set-cookie")
    session = _set_cookie_header(headers, AUTH_COOKIE_NAME)
    csrf = _set_cookie_header(headers, CSRF_COOKIE_NAME)
    assert "Max-Age=0" in session and "Path=/api" in session
    assert "Max-Age=0" in csrf and "Path=/" in csrf
    assert client.get("/api/user/me").status_code == 401


async def test_existing_session_observes_committed_role_change(client, user, db_session_factory):
    login(client, user.username)
    assert client.get("/api/admin/users").status_code == 200
    async with db_session_factory() as session:
        account = await session.get(User, user.id)
        assert account is not None
        account.role = UserRole.ADMIN
        await session.commit()
    assert client.get("/api/user/me").json()["role"] == "admin"
    assert client.get("/api/admin/users").status_code == 403


async def test_deleted_account_session_is_rejected_after_id_reuse(client, user, db_session_factory):
    login(client, user.username)
    async with db_session_factory() as session:
        assert await delete_user(session, user.id)
    assert client.get("/api/user/me").status_code == 401
    async with db_session_factory() as session:
        session.add(User(id=user.id, username=user.username, hashed_password="unused", role=UserRole.OWNER,
                         created_at=datetime(2026, 1, 2, tzinfo=UTC)))
        await session.commit()
    assert client.get("/api/user/me").status_code == 401
    response = client.get("/api/user/me", headers={"Authorization": f"Bearer {get_settings().master_token}"})
    assert response.status_code == 200
    assert response.json()["username"] == "SYSTEM"


def test_code_login_uses_persisted_account_and_consumes_code_and_ticket_once(client, user, isolated_runtime, caplog):
    from httpx2 import ASGITransport, AsyncClient

    async def verify(code):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as verifier:
            return await verifier.post(
                "/api/auth/verifyCode", headers={"Authorization": f"Bearer {get_settings().master_token}"},
                json={"username": user.username, "code": code},
            )

    with client.websocket_connect("/api/auth/code") as websocket:
        code = websocket.receive_json()["code"]
        assert client.get("/api/user/me").status_code == 401
        response = websocket.portal.call(verify, code)
        assert response.status_code == 200
        verified = websocket.receive_json()
        assert verified["type"] == "verified"
        ticket = verified["ticket"]
        assert websocket.portal.call(verify, code).status_code == 400
        completed = client.post("/api/auth/code/complete", json={"ticket": ticket})
        assert completed.status_code == 200
        assert completed.json()["user"]["id"] == user.id
        assert client.get("/api/user/me").json()["username"] == user.username
        assert client.post("/api/auth/code/complete", json={"ticket": ticket}).status_code == 400
    assert isolated_runtime.login_code_manager.websocket_code_map == {}
    assert isolated_runtime.login_code_manager.completion_tickets == {}
    assert code not in caplog.text and ticket not in caplog.text
