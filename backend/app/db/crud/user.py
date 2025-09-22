from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...models import User


async def get_user_by_username(session: AsyncSession, username: str) -> User | None:
    """Get user by username."""
    result = await session.scalars(select(User).where(User.username == username))
    return result.first()


async def get_user_by_id(session: AsyncSession, user_id: int) -> User | None:
    """Get user by ID."""
    result = await session.scalars(select(User).where(User.id == user_id))
    return result.first()


async def get_all_users(session: AsyncSession) -> list[User]:
    """Get all users."""
    result = await session.scalars(select(User).order_by(User.id))
    return list(result.all())


async def create_user(session: AsyncSession, user: User) -> User:
    """Create a new user."""
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def delete_user(session: AsyncSession, user_id: int) -> bool:
    """Delete a user by ID. Returns True if deleted, False if not found."""
    user = await get_user_by_id(session, user_id)
    if user is None:
        return False

    await session.delete(user)
    await session.commit()
    return True
