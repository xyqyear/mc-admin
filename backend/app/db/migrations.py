import asyncio
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from ..config import settings
from ..models import Base


def _sync_database_url() -> str:
    if settings.database_url.startswith("sqlite+aiosqlite:///"):
        return settings.database_url.replace("sqlite+aiosqlite:///", "sqlite:///")
    return settings.database_url


def _alembic_config() -> Config:
    backend_dir = Path(__file__).resolve().parents[2]
    return Config(str(backend_dir / "alembic.ini"))


def _ensure_database_schema_sync() -> None:
    engine = create_engine(_sync_database_url())

    try:
        with engine.begin() as connection:
            tables = set(inspect(connection).get_table_names())
            alembic_cfg = _alembic_config()
            alembic_cfg.attributes["connection"] = connection

            if not tables:
                Base.metadata.create_all(connection)
                command.stamp(alembic_cfg, "head")
                return

            if "alembic_version" not in tables:
                raise RuntimeError(
                    "Database schema exists but is not managed by Alembic. "
                    "Manual migration is required before startup."
                )

            command.upgrade(alembic_cfg, "head")
    finally:
        engine.dispose()


async def ensure_database_schema() -> None:
    await asyncio.to_thread(_ensure_database_schema_sync)
