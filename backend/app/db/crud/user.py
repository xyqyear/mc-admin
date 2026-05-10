from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...models import User


async def get_user_by_username(session: AsyncSession, username: str) -> User | None:
    result = await session.scalars(select(User).where(User.username == username))
    return result.first()


async def get_user_by_id(session: AsyncSession, user_id: int) -> User | None:
    result = await session.scalars(select(User).where(User.id == user_id))
    return result.first()


async def get_all_users(session: AsyncSession) -> list[User]:
    result = await session.scalars(select(User).order_by(User.id))
    return list(result.all())


async def create_user(session: AsyncSession, user: User) -> User:
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def delete_user(session: AsyncSession, user_id: int) -> bool:
    """Returns ``True`` if the user existed and was deleted."""
    user = await get_user_by_id(session, user_id)
    if user is None:
        return False

    await session.delete(user)
    await session.commit()
    return True
