from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from app.db.database import Database
from app.db.metadata import Base


async def initialize_database(database: Database) -> None:
    async with database.engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


@asynccontextmanager
async def database_at(path: Path) -> AsyncGenerator[Database]:
    database = Database(f"sqlite+aiosqlite:///{path}")
    try:
        await initialize_database(database)
        yield database
    finally:
        await database.close()
