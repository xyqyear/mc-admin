from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...models import User


async def get_user_by_username(session: AsyncSession, username: str) -> User | None:
    """Get user by username."""
    result = await session.scalars(
        select(User).where(User.username == username)
    )
    return result.first()


async def get_user_by_id(session: AsyncSession, user_id: int) -> User | None:
    """Get user by ID."""
    result = await session.scalars(
        select(User).where(User.id == user_id)
    )
    return result.first()


async def create_user(session: AsyncSession, user: User) -> User:
    """Create a new user."""
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user
