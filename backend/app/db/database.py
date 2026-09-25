import re
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from ..runtime_resources import current_runtime


class Database:
    def __init__(self, url: str) -> None:
        async_url = re.sub(r"^sqlite:///", "sqlite+aiosqlite:///", url)
        self.engine = create_async_engine(async_url, echo=False, hide_parameters=True)
        self.session_factory = async_sessionmaker(
            bind=self.engine, class_=AsyncSession, autocommit=False,
            autoflush=False, expire_on_commit=False,
        )

    async def close(self) -> None:
        await self.engine.dispose()


def get_database() -> Database:
    return current_runtime().resource('database')
def get_engine() -> AsyncEngine:
    return current_runtime().resource('database_engine')
def get_session_factory() -> async_sessionmaker[AsyncSession]:
    return current_runtime().resource('session_factory')


async def get_db() -> AsyncGenerator[AsyncSession]:
    """FastAPI dependency for async database sessions."""
    async with get_session_factory()() as session:
        yield session


def get_async_session():
    """Async session context manager for use outside FastAPI dependency injection."""
    return get_session_factory()()
