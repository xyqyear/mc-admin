"""
Configuration migration system for version management and field handling.
"""

import logging
from typing import Any, Dict, List, Tuple, Type

from .schemas import BaseConfigSchema

logger = logging.getLogger(__name__)


class ConfigMigrator:
    """
    Handles configuration migration between schema versions.

    Responsibilities:
    - Compare schema versions
    - Validate configuration data using Pydantic model validation
    """

    @staticmethod
    def migrate_config(
        current_data: Dict[str, Any],
        schema_cls: Type[BaseConfigSchema],
        stored_version: str,
    ) -> Tuple[Dict[str, Any], List[str]]:
        """
        Migrate configuration data to match the current schema.

        Args:
            current_data: Current configuration data from database
            schema_cls: Target schema class
            stored_version: Version of the stored configuration

        Returns:
            Tuple of (migrated_data, migration_messages)
        """
        current_version = schema_cls.get_schema_version()
        migration_messages = []

        # If versions match, no migration needed
        if stored_version == current_version:
            return current_data, migration_messages

        migration_messages.append(
            f"Migrating {schema_cls.__name__} from version {stored_version} to {current_version}"
        )
        logger.info(
            f"Starting migration for {schema_cls.__name__}: {stored_version} -> {current_version}"
        )

        # Use Pydantic model validation to migrate the data
        try:
            migrated_instance = schema_cls.model_validate(current_data)
            migrated_data = migrated_instance.model_dump()
        except Exception as e:
            logger.error(f"Migration failed for {schema_cls.__name__}: {e}")
            raise ValueError(f"Failed to migrate configuration: {e}")

        logger.info(f"Migration completed for {schema_cls.__name__}")
        return migrated_data, migration_messages

    @staticmethod
    def create_default_config(schema_cls: Type[BaseConfigSchema]) -> Dict[str, Any]:
        """
        Create a default configuration dictionary for the given schema.

        Args:
            schema_cls: Schema class to create defaults for

        Returns:
            Dictionary with all fields set to their default values
        """
        # Create an instance with all defaults
        instance = schema_cls()
        return instance.model_dump()

    @staticmethod
    def validate_config(
        data: Dict[str, Any], schema_cls: Type[BaseConfigSchema]
    ) -> List[str]:
        """
        Validate configuration data against schema without migration.

        Args:
            data: Configuration data to validate
            schema_cls: Schema to validate against

        Returns:
            List of validation error messages (empty if valid)
        """
        try:
            # Try to create instance - this will validate all fields
            schema_cls.model_validate(data)
            return []
        except Exception as e:
            return [str(e)]
