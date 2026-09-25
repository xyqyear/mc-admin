import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.metadata import Base
from app.operations.journal import OperationJournal


@pytest.fixture
async def journal(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'operations.sqlite3'}", hide_parameters=True)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    try:
        yield OperationJournal(async_sessionmaker(engine, expire_on_commit=False))
    finally:
        await engine.dispose()
