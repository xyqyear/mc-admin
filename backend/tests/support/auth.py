from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth.jwt_utils import get_password_hash
from app.auth.models import User, UserRole
from app.auth.schemas import UserPublic
from app.auth.service import user_to_public
from app.auth.session import CSRF_COOKIE_NAME, CSRF_HEADER_NAME

PASSWORD = "synthetic-test-password"


async def create_account(
    sessions: async_sessionmaker[AsyncSession], *, username: str = "owner",
    role: UserRole = UserRole.OWNER,
) -> UserPublic:
    async with sessions() as session:
        user = User(
            username=username, hashed_password=get_password_hash(PASSWORD), role=role,
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user_to_public(user)


def login(client: TestClient, username: str = "owner", *, prefix: str = "/api"):
    response = client.post(
        f"{prefix}/auth/token",
        data={"grant_type": "password", "username": username, "password": PASSWORD},
    )
    assert response.status_code == 200, response.text
    client.headers[CSRF_HEADER_NAME] = client.cookies[CSRF_COOKIE_NAME]
    return response
