"""
Dynamic configuration manager with memory caching and database synchronization.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Type

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.database import get_async_session
from ..models import DynamicConfig
from .migration import ConfigMigrator
from .schemas import BaseConfigSchema

logger = logging.getLogger(__name__)


class ConfigManager:
    """
    Central manager for dynamic configuration with memory caching.

    Features:
    - In-memory configuration caching
    - Database persistence
    - Automatic schema migration on startup
    - Configuration validation
    - Thread-safe access to configurations
    """

    def __init__(self):
        """Initialize the configuration manager."""
        self._configs: Dict[str, BaseConfigSchema] = {}
        self._schemas: Dict[str, Type[BaseConfigSchema]] = {}
        self._initialized = False

    def register_config(
        self, module_name: str, schema_cls: Type[BaseConfigSchema]
    ) -> None:
        """
        Register a configuration schema for a module.

        Args:
            module_name: Unique identifier for the configuration module
            schema_cls: Pydantic schema class inheriting from BaseConfigSchema

        Raises:
            ValueError: If module_name already registered or schema_cls invalid
        """
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
        """
        Initialize all registered configurations.

        This method:
        1. Loads configurations from database
        2. Performs version migration if needed
        3. Creates default configs for new modules
        4. Caches all configurations in memory
        5. Updates database with migrated configurations

        Should be called once during application startup.
        """
        if self._initialized:
            logger.warning("ConfigManager already initialized, skipping...")
            return

        if not self._schemas:
            logger.warning("No configuration schemas registered")
            self._initialized = True
            return

        logger.info(f"Initializing {len(self._schemas)} configuration modules...")

        async with get_async_session() as session:
            # Load all existing configurations from database
            result = await session.execute(select(DynamicConfig))
            existing_configs = {
                config.module_name: config for config in result.scalars().all()
            }

            for module_name, schema_cls in self._schemas.items():
                try:
                    if module_name in existing_configs:
                        # Migrate existing configuration
                        await self._load_and_migrate_config(
                            session,
                            module_name,
                            schema_cls,
                            existing_configs[module_name],
                        )
                    else:
                        # Create new configuration with defaults
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
        session: AsyncSession,
        module_name: str,
        schema_cls: Type[BaseConfigSchema],
        db_config: DynamicConfig,
    ) -> None:
        """
        Load configuration from database and perform migration if needed.

        Args:
            session: Database session
            module_name: Module name
            schema_cls: Target schema class
            db_config: Existing database configuration
        """
        logger.info(f"Loading configuration for module '{module_name}'")

        # Perform migration
        migrated_data, migration_messages = ConfigMigrator.migrate_config(
            db_config.config_data, schema_cls, db_config.config_schema_version
        )

        # Log migration messages
        for message in migration_messages:
            logger.info(f"Migration '{module_name}': {message}")

        # Create validated configuration instance
        config_instance = schema_cls.model_validate(migrated_data)
        self._configs[module_name] = config_instance

        # Update database if migration occurred
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
        """
        Create a new configuration with default values.

        Args:
            session: Database session
            module_name: Module name
            schema_cls: Schema class
        """
        logger.info(f"Creating default configuration for new module '{module_name}'")

        # Create default configuration
        default_data = ConfigMigrator.create_default_config(schema_cls)
        config_instance = schema_cls.model_validate(default_data)
        self._configs[module_name] = config_instance

        # Save to database
        db_config = DynamicConfig(
            module_name=module_name,
            config_data=default_data,
            config_schema_version=schema_cls.get_schema_version(),
            updated_at=datetime.now(timezone.utc),
        )
        session.add(db_config)
        logger.info(f"Created default configuration for module '{module_name}'")

    async def update_config(
        self, module_name: str, new_data: Dict[str, Any]
    ) -> BaseConfigSchema:
        """
        Update configuration for a module.

        Args:
            module_name: Module name to update
            new_data: New configuration data

        Returns:
            Updated configuration instance

        Raises:
            ValueError: If module not registered or data invalid
        """
        if not self._initialized:
            raise RuntimeError(
                "ConfigManager not initialized. Call initialize_all_configs() first."
            )

        if module_name not in self._schemas:
            raise ValueError(f"Module '{module_name}' not registered")

        schema_cls = self._schemas[module_name]

        # Validate new data
        try:
            new_config_instance = schema_cls.model_validate(new_data)
        except Exception as e:
            raise ValueError(
                f"Invalid configuration data for module '{module_name}': {e}"
            )

        # Update database
        async with get_async_session() as session:
            result = await session.execute(
                select(DynamicConfig).where(DynamicConfig.module_name == module_name)
            )
            db_config = result.scalar_one_or_none()

            if db_config:
                db_config.config_data = new_data
                db_config.config_schema_version = schema_cls.get_schema_version()
                db_config.updated_at = datetime.now(timezone.utc)
            else:
                # Should not happen if properly initialized, but handle gracefully
                db_config = DynamicConfig(
                    module_name=module_name,
                    config_data=new_data,
                    config_schema_version=schema_cls.get_schema_version(),
                    updated_at=datetime.now(timezone.utc),
                )
                session.add(db_config)

            await session.commit()

        # Update memory cache
        self._configs[module_name] = new_config_instance

        logger.info(f"Updated configuration for module '{module_name}'")
        return new_config_instance

    def get_config(self, module_name: str) -> BaseConfigSchema:
        """
        Get configuration instance for a module.

        Args:
            module_name: Module name

        Returns:
            Configuration instance with type safety

        Raises:
            ValueError: If module not registered
            RuntimeError: If manager not initialized
        """
        if not self._initialized:
            raise RuntimeError(
                "ConfigManager not initialized. Call initialize_all_configs() first."
            )

        if module_name not in self._configs:
            raise ValueError(f"Configuration for module '{module_name}' not found")

        return self._configs[module_name]

    def get_all_configs(self) -> Dict[str, BaseConfigSchema]:
        """
        Get all configuration instances.

        Returns:
            Dictionary mapping module names to configuration instances

        Raises:
            RuntimeError: If manager not initialized
        """
        if not self._initialized:
            raise RuntimeError(
                "ConfigManager not initialized. Call initialize_all_configs() first."
            )

        return self._configs.copy()

    def get_schema_info(self, module_name: str) -> Dict[str, Any]:
        """
        Get schema information for a module.

        Args:
            module_name: Module name

        Returns:
            Dictionary with schema metadata

        Raises:
            ValueError: If module not registered
        """
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
        """
        Get schema information for all registered modules.

        Returns:
            Dictionary mapping module names to schema information
        """
        return {
            module_name: self.get_schema_info(module_name)
            for module_name in self._schemas.keys()
        }

    async def reset_config(self, module_name: str) -> BaseConfigSchema:
        """
        Reset configuration to default values.

        Args:
            module_name: Module name to reset

        Returns:
            Reset configuration instance

        Raises:
            ValueError: If module not registered
        """
        if module_name not in self._schemas:
            raise ValueError(f"Module '{module_name}' not registered")

        schema_cls = self._schemas[module_name]
        default_data = ConfigMigrator.create_default_config(schema_cls)

        return await self.update_config(module_name, default_data)


# Global configuration manager instance
config_manager = ConfigManager()
