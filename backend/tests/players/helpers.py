import hashlib
import tempfile
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.metadata import Base


def make_online_uuid(seed: str) -> str:
    source = hashlib.md5(seed.encode()).hexdigest()
    return f"{source[:12]}4{source[13:16]}8{source[17:]}"


def make_offline_uuid(seed: str) -> str:
    source = hashlib.md5(seed.encode()).hexdigest()
    return f"{source[:12]}3{source[13:16]}8{source[17:]}"


async def create_test_db():
    """Create a temporary test database and return session."""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as temp_db:
        temp_db_path = Path(temp_db.name)

    database_url = f"sqlite+aiosqlite:///{temp_db_path}"
    engine = create_async_engine(database_url, echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    session = async_session()

    return session, engine, temp_db_path

async def cleanup_test_db(session, engine, temp_db_path):
    """Cleanup test database."""
    await session.close()
    await engine.dispose()
    temp_db_path.unlink(missing_ok=True)
