import os
import sys
from logging.config import fileConfig

from sqlalchemy import Connection, engine_from_config, pool

from alembic import context

# Add the project root to the path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

# Import your model's MetaData object
from app.config import Settings
from app.db.metadata import Base
from app.runtime_resources import bound_runtime

config = context.config

runtime = bound_runtime()
settings = runtime.settings if runtime is not None else Settings()  # type: ignore
database_url = settings.database_url
if database_url.startswith('sqlite+aiosqlite:///'):
    database_url = database_url.replace('sqlite+aiosqlite:///', 'sqlite:///')
config.set_main_option('sqlalchemy.url', database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Emit migration SQL without constructing an engine or requiring a DBAPI."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = config.attributes.get("connection")

    if isinstance(connectable, Connection):
        context.configure(
            connection=connectable, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()
        return

    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    try:
        with connectable.connect() as connection:
            context.configure(connection=connection, target_metadata=target_metadata)

            with context.begin_transaction():
                context.run_migrations()
    finally:
        connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
