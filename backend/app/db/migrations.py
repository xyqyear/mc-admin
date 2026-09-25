import asyncio
import threading
from pathlib import Path

from alembic.config import Config
from sqlalchemy import create_engine, inspect

from alembic import command

from ..config import get_settings
from ..operations.finalization import finalize
from .metadata import Base

# Alembic's EnvironmentContext proxy is process-global even for different databases.
_migration_lock = threading.Lock()


def _sync_database_url() -> str:
    settings = get_settings()
    if settings.database_url.startswith("sqlite+aiosqlite:///"):
        return settings.database_url.replace("sqlite+aiosqlite:///", "sqlite:///")
    return settings.database_url


def _alembic_config() -> Config:
    backend_dir = Path(__file__).resolve().parents[2]
    return Config(str(backend_dir / "alembic.ini"))


def _ensure_database_schema_sync() -> None:
    with _migration_lock:
        _migrate_owned_database()


def _migrate_owned_database() -> None:
    engine = create_engine(_sync_database_url(), hide_parameters=True)

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
    await finalize(asyncio.to_thread(_ensure_database_schema_sync))
