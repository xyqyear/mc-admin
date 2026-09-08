from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.auth.session import (
    AUTH_COOKIE_NAME,
    CSRF_COOKIE_NAME,
    CSRF_HEADER_NAME,
    create_session_token,
)
from app.config import settings
from app.db.database import get_db
from app.main import api_app, app
from app.models import User, UserPublic, UserRole

MASTER_TOKEN = "test-master-token"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(settings, "master_token", MASTER_TOKEN)
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def user(monkeypatch):
    user = UserPublic(
        id=42,
        username="owner",
        role=UserRole.OWNER,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    monkeypatch.setattr(
        "app.auth.session._get_current_session_user", AsyncMock(return_value=user)
    )
    return user


def _set_session_cookies(client: TestClient, user: UserPublic) -> str:
    token, csrf_token = create_session_token(user)
    client.cookies.set(AUTH_COOKIE_NAME, token, path="/api")
    client.cookies.set(CSRF_COOKIE_NAME, csrf_token, path="/")
    return csrf_token


def _set_cookie_header(headers: list[str], name: str) -> str:
    return next(header for header in headers if header.startswith(f"{name}="))


def test_session_cookie_authenticates_current_user(client, user):
    _set_session_cookies(client, user)

    response = client.get("/api/user/me")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == user.id
    assert data["username"] == user.username
    assert data["role"] == user.role.value


def test_current_user_requires_authentication(client):
    response = client.get("/api/user/me")

    assert response.status_code == 401


def test_master_token_takes_precedence_over_stale_session_cookie(client):
    client.cookies.set(AUTH_COOKIE_NAME, "stale-session", path="/api")

    response = client.get(
        "/api/user/me",
        headers={"Authorization": f"Bearer {MASTER_TOKEN}"},
    )

    assert response.status_code == 200
    assert response.json()["username"] == "SYSTEM"


def test_password_login_sets_auth_cookies_without_returning_token(client):
    async def override_get_db():
        yield object()

    db_user = User(
        id=7,
        username="owner",
        hashed_password="hash",
        role=UserRole.OWNER,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    api_app.dependency_overrides[get_db] = override_get_db
    try:
        with (
            patch(
                "app.routers.auth.get_user_by_username",
                new=AsyncMock(return_value=db_user),
            ),
            patch("app.routers.auth.verify_password", return_value=True),
        ):
            response = client.post(
                "/api/auth/token",
                data={
                    "grant_type": "password",
                    "username": "owner",
                    "password": "secret",
                },
            )
    finally:
        api_app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200
    data = response.json()
    assert data["user"]["username"] == "owner"
    assert "access_token" not in data
    assert "token_type" not in data

    set_cookie_headers = response.headers.get_list("set-cookie")
    session_cookie = _set_cookie_header(set_cookie_headers, AUTH_COOKIE_NAME)
    csrf_cookie = _set_cookie_header(set_cookie_headers, CSRF_COOKIE_NAME)

    assert "HttpOnly" in session_cookie
    assert "Path=/api" in session_cookie
    assert "HttpOnly" not in csrf_cookie
    assert "Path=/" in csrf_cookie


def test_unsafe_cookie_request_requires_csrf_header(client, user):
    _set_session_cookies(client, user)

    response = client.post("/api/user/me")

    assert response.status_code == 403
    assert response.json()["detail"] == "Missing CSRF token"


def test_unsafe_cookie_request_rejects_invalid_csrf_header(client, user):
    _set_session_cookies(client, user)

    response = client.post(
        "/api/user/me",
        headers={CSRF_HEADER_NAME: "wrong-token"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Invalid CSRF token"


def test_unsafe_cookie_request_accepts_matching_csrf_header(client, user):
    csrf_token = _set_session_cookies(client, user)

    response = client.post(
        "/api/user/me",
        headers={CSRF_HEADER_NAME: csrf_token},
    )

    assert response.status_code == 405


def test_logout_clears_auth_cookies(client, user):
    _set_session_cookies(client, user)

    response = client.post("/api/auth/logout")

    assert response.status_code == 204
    set_cookie_headers = response.headers.get_list("set-cookie")
    session_cookie = _set_cookie_header(set_cookie_headers, AUTH_COOKIE_NAME)
    csrf_cookie = _set_cookie_header(set_cookie_headers, CSRF_COOKIE_NAME)

    assert "Max-Age=0" in session_cookie
    assert "Path=/api" in session_cookie
    assert "Max-Age=0" in csrf_cookie
    assert "Path=/" in csrf_cookie


@pytest.mark.asyncio
async def test_deleted_account_session_is_rejected_after_id_reuse(client, tmp_path, monkeypatch):
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.auth.session import user_to_public
    from app.db.crud.user import create_user, delete_user

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'auth.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(User.metadata.tables["user"].create)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr("app.auth.session.get_async_session", sessions)
    try:
        async with sessions() as session:
            db_user = await create_user(session, User(
                username="removed", hashed_password="unused", role=UserRole.ADMIN,
                created_at=datetime(2026, 1, 1, tzinfo=UTC),
            ))
            identity = user_to_public(db_user)
            _set_session_cookies(client, identity)
            assert client.get("/api/user/me").status_code == 200
            assert await delete_user(session, identity.id)
        assert client.get("/api/user/me").status_code == 401
        async with sessions() as session:
            await create_user(session, User(
                id=identity.id, username=identity.username, hashed_password="replacement",
                role=UserRole.OWNER, created_at=datetime(2026, 1, 2, tzinfo=UTC),
            ))
        assert client.get("/api/user/me").status_code == 401
        response = client.get("/api/user/me", headers={"Authorization": f"Bearer {MASTER_TOKEN}"})
        assert response.status_code == 200
        assert response.json()["username"] == "SYSTEM"
    finally:
        await engine.dispose()
