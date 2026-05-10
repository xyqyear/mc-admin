"""Dynamic configuration manager: in-memory cache backed by the database."""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Type

from sqlalchemy.ext.asyncio import AsyncSession

from ..db.database import get_async_session

from . import crud
from .migration import ConfigMigrator
from .schemas import BaseConfigSchema

logger = logging.getLogger(__name__)


class ConfigManager:
    """In-memory cache of registered config modules with DB persistence and schema migration."""

    def __init__(self):
        self._configs: Dict[str, BaseConfigSchema] = {}
        self._schemas: Dict[str, Type[BaseConfigSchema]] = {}
        self._initialized = False

    def register_config(
        self, module_name: str, schema_cls: Type[BaseConfigSchema]
    ) -> None:
        if not issubclass(schema_cls, BaseConfigSchema):
            raise ValueError(
                f"Schema class {schema_cls} must inherit from BaseConfigSchema"
            )

        if module_name in self._schemas:
            raise ValueError(
                f"Configuration module '{module_name}' is already registered"
            )

        self._schemas[module_name] = schema_cls
        logger.info(
            f"Registered configuration schema for module '{module_name}': {schema_cls.__name__}"
        )

    async def initialize_all_configs(self) -> None:
        """Load each registered config from DB, migrate, or create defaults; cache in memory."""
        if self._initialized:
            logger.warning("ConfigManager already initialized, skipping...")
            return

        if not self._schemas:
            logger.warning("No configuration schemas registered")
            self._initialized = True
            return

        logger.info(f"Initializing {len(self._schemas)} configuration modules...")

        async with get_async_session() as session:
            existing_configs = await crud.get_all_configs(session)

            for module_name, schema_cls in self._schemas.items():
                try:
                    if module_name in existing_configs:
                        await self._load_and_migrate_config(
                            module_name,
                            schema_cls,
                            existing_configs[module_name],
                        )
                    else:
                        await self._create_default_config(
                            session, module_name, schema_cls
                        )
                except Exception as e:
                    logger.error(
                        f"Failed to initialize configuration for module '{module_name}': {e}"
                    )
                    raise

            await session.commit()

        self._initialized = True
        logger.info("All configurations initialized successfully")

    async def _load_and_migrate_config(
        self,
        module_name: str,
        schema_cls: Type[BaseConfigSchema],
        db_config,
    ) -> None:
        """Load ``db_config``, run any schema migration, and write back if it changed."""
        logger.info(f"Loading configuration for module '{module_name}'")

        migrated_data, migration_messages = ConfigMigrator.migrate_config(
            db_config.config_data, schema_cls, db_config.config_schema_version
        )

        for message in migration_messages:
            logger.info(f"Migration '{module_name}': {message}")

        config_instance = schema_cls.model_validate(migrated_data)
        self._configs[module_name] = config_instance

        current_version = schema_cls.get_schema_version()
        if db_config.config_schema_version != current_version or migration_messages:
            db_config.config_data = migrated_data
            db_config.config_schema_version = current_version
            db_config.updated_at = datetime.now(timezone.utc)
            logger.info(
                f"Updated database configuration for module '{module_name}' to version {current_version}"
            )

    async def _create_default_config(
        self,
        session: AsyncSession,
        module_name: str,
        schema_cls: Type[BaseConfigSchema],
    ) -> None:
        logger.info(f"Creating default configuration for new module '{module_name}'")

        default_data = ConfigMigrator.create_default_config(schema_cls)
        config_instance = schema_cls.model_validate(default_data)
        self._configs[module_name] = config_instance

        await crud.create_config(
            session,
            module_name=module_name,
            config_data=default_data,
            config_schema_version=schema_cls.get_schema_version(),
        )
        logger.info(f"Created default configuration for module '{module_name}'")

    async def update_config(
        self, module_name: str, new_data: Dict[str, Any]
    ) -> BaseConfigSchema:
        """Validate, persist, and cache ``new_data`` for ``module_name``."""
        if not self._initialized:
            raise RuntimeError(
                "ConfigManager not initialized. Call initialize_all_configs() first."
            )

        if module_name not in self._schemas:
            raise ValueError(f"Module '{module_name}' not registered")

        schema_cls = self._schemas[module_name]

        try:
            new_config_instance = schema_cls.model_validate(new_data)
        except Exception as e:
            raise ValueError(
                f"Invalid configuration data for module '{module_name}': {e}"
            )

        async with get_async_session() as session:
            await crud.upsert_config(
                session,
                module_name,
                new_data,
                schema_cls.get_schema_version(),
            )

        self._configs[module_name] = new_config_instance

        logger.info(f"Updated configuration for module '{module_name}'")
        return new_config_instance

    def get_config(self, module_name: str) -> BaseConfigSchema:
        if not self._initialized:
            raise RuntimeError(
                "ConfigManager not initialized. Call initialize_all_configs() first."
            )

        if module_name not in self._configs:
            raise ValueError(f"Configuration for module '{module_name}' not found")

        return self._configs[module_name]

    def get_all_configs(self) -> Dict[str, BaseConfigSchema]:
        if not self._initialized:
            raise RuntimeError(
                "ConfigManager not initialized. Call initialize_all_configs() first."
            )

        return self._configs.copy()

    def get_schema_info(self, module_name: str) -> Dict[str, Any]:
        if module_name not in self._schemas:
            raise ValueError(f"Module '{module_name}' not registered")

        schema_cls = self._schemas[module_name]
        return {
            "module_name": module_name,
            "schema_class": schema_cls.__name__,
            "version": schema_cls.get_schema_version(),
            "json_schema": schema_cls.model_json_schema(),
        }

    def get_all_schema_info(self) -> Dict[str, Dict[str, Any]]:
        return {
            module_name: self.get_schema_info(module_name)
            for module_name in self._schemas.keys()
        }

    async def reset_config(self, module_name: str) -> BaseConfigSchema:
        if module_name not in self._schemas:
            raise ValueError(f"Module '{module_name}' not registered")

        schema_cls = self._schemas[module_name]
        default_data = ConfigMigrator.create_default_config(schema_cls)

        return await self.update_config(module_name, default_data)


config_manager = ConfigManager()
