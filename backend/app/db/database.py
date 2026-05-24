import re
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ..config import settings
from ..models import Base

# SQLite needs the aiosqlite driver for async access.
async_database_url = re.sub(
    r"^sqlite:///", "sqlite+aiosqlite:///", settings.database_url
)
engine = create_async_engine(async_database_url, echo=True)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency for async database sessions."""
    async with AsyncSessionLocal() as session:
        yield session


def get_async_session():
    """Async session context manager for use outside FastAPI dependency injection."""
    return AsyncSessionLocal()
