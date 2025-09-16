"""
Integration tests for the dynamic configuration system with real database.
"""

import tempfile
from pathlib import Path
from typing import List, cast

import pytest
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.dynamic_config import BaseConfigSchema
from app.dynamic_config.manager import ConfigManager
from app.models import Base, DynamicConfig


# Test configuration schemas with nested structures and deprecated fields
class NestedTestConfig(BaseConfigSchema):
    """Nested configuration for testing."""

    value: str = Field(default="nested_default", description="A nested value")
    number: int = Field(default=42, description="A nested number")
    deprecated_nested: str = Field(
        default="old_nested_value",
        description="A deprecated nested field",
        deprecated="Use value instead",
    )


class ListItemTestConfig(BaseConfigSchema):
    """Configuration for list items."""

    name: str = Field(description="Item name")
    priority: int = Field(default=1, description="Item priority")
    deprecated_item: str = Field(
        default="old_item",
        description="Deprecated item field",
        deprecated="This field is no longer used",
    )


class ComplexTestConfig(BaseConfigSchema):
    """Complex configuration with nested models, lists, and deprecated fields."""

    simple_field: str = Field(default="test_value", description="A simple field")

    # Nested configuration
    nested: NestedTestConfig = Field(
        default_factory=NestedTestConfig, description="Nested configuration"
    )

    # List of nested configurations
    items: List[ListItemTestConfig] = Field(default=[], description="List of items")

    # Regular list
    tags: List[str] = Field(default=["default"], description="List of tags")

    # Deprecated field at top level
    deprecated_field: str = Field(
        default="deprecated_value",
        description="A deprecated field",
        deprecated="Use simple_field instead",
    )


class SimpleTestConfig(BaseConfigSchema):
    """Simple configuration for basic testing."""

    name: str = Field(default="simple_test", description="Configuration name")
    enabled: bool = Field(default=True, description="Whether enabled")
    count: int = Field(default=10, description="Count value")


@pytest.fixture(scope="function")
async def test_db_engine():
    """Create a test database engine."""
    # Create temporary database file
    temp_db = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    temp_db.close()

    database_url = f"sqlite+aiosqlite:///{temp_db.name}"
    engine = create_async_engine(database_url, echo=False)

    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    # Cleanup
    await engine.dispose()
    Path(temp_db.name).unlink(missing_ok=True)


@pytest.fixture
async def test_db_session(test_db_engine):
    """Create a test database session."""
    TestSessionLocal = async_sessionmaker(
        bind=test_db_engine,
        class_=AsyncSession,
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
    )

    async with TestSessionLocal() as session:
        yield session


@pytest.fixture
async def test_config_manager(test_db_engine):
    """Create a test configuration manager with test database."""
    # Create new manager instance for testing
    manager = ConfigManager()

    # Monkey patch the database session to use test database
    TestSessionLocal = async_sessionmaker(
        bind=test_db_engine,
        class_=AsyncSession,
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
    )

    # Patch get_async_session to use test database
    from unittest.mock import patch

    with patch("app.dynamic_config.manager.get_async_session") as mock_get_session:
        def get_test_session():
            return TestSessionLocal()

        mock_get_session.side_effect = get_test_session

        # Register test configurations
        manager.register_config("simple", SimpleTestConfig)
        manager.register_config("complex", ComplexTestConfig)

        yield manager


class TestConfigManagerIntegration:
    """Integration tests for ConfigManager with real database."""

    @pytest.mark.asyncio
    async def test_initialize_new_configs(self, test_config_manager):
        """Test initializing new configurations creates defaults in database."""
        manager = test_config_manager

        # Initialize configurations
        await manager.initialize_all_configs()

        # Verify manager is initialized
        assert manager._initialized

        # Check simple config
        simple_config = manager.get_config("simple")
        assert simple_config.name == "simple_test"
        assert simple_config.enabled is True
        assert simple_config.count == 10

        # Check complex config with nested structures
        complex_config = manager.get_config("complex")
        assert complex_config.simple_field == "test_value"
        assert complex_config.nested.value == "nested_default"
        assert complex_config.nested.number == 42
        assert complex_config.nested.deprecated_nested == "old_nested_value"
        assert complex_config.items == []
        assert complex_config.tags == ["default"]
        assert complex_config.deprecated_field == "deprecated_value"

    @pytest.mark.asyncio
    async def test_database_storage(self, test_config_manager, test_db_session):
        """Test that configurations are properly stored in database."""
        manager = test_config_manager
        await manager.initialize_all_configs()

        # Check database records
        result = await test_db_session.execute(select(DynamicConfig))
        configs = result.scalars().all()

        assert len(configs) == 2

        # Find configs by module name
        simple_db = next(c for c in configs if c.module_name == "simple")
        complex_db = next(c for c in configs if c.module_name == "complex")

        # Verify simple config data
        assert simple_db.config_data["name"] == "simple_test"
        assert simple_db.config_data["enabled"] is True
        assert simple_db.config_data["count"] == 10
        assert simple_db.config_schema_version == SimpleTestConfig.get_schema_version()

        # Verify complex config data structure
        complex_data = complex_db.config_data
        assert complex_data["simple_field"] == "test_value"
        assert complex_data["nested"]["value"] == "nested_default"
        assert complex_data["nested"]["number"] == 42
        assert complex_data["nested"]["deprecated_nested"] == "old_nested_value"
        assert complex_data["items"] == []
        assert complex_data["tags"] == ["default"]
        assert complex_data["deprecated_field"] == "deprecated_value"
        assert (
            complex_db.config_schema_version == ComplexTestConfig.get_schema_version()
        )

    @pytest.mark.asyncio
    async def test_config_migration_add_fields(
        self, test_config_manager, test_db_session
    ):
        """Test migration adds missing fields with defaults."""
        manager = test_config_manager

        # Create old config data missing some fields
        old_data = {"name": "old_name", "enabled": False}  # missing 'count'

        # Insert old config directly into database
        old_config = DynamicConfig(
            module_name="simple",
            config_data=old_data,
            config_schema_version="old_version_123",
        )
        test_db_session.add(old_config)
        await test_db_session.commit()

        # Initialize should trigger migration
        await manager.initialize_all_configs()

        # Check migrated config
        config = manager.get_config("simple")
        assert config.name == "old_name"  # preserved
        assert config.enabled is False  # preserved
        assert config.count == 10  # added default

    @pytest.mark.asyncio
    async def test_config_migration_remove_obsolete_fields(
        self, test_config_manager, test_db_session
    ):
        """Test migration removes obsolete fields not in schema."""
        manager = test_config_manager

        # Create config data with obsolete fields
        old_data = {
            "name": "test_name",
            "enabled": True,
            "count": 5,
            "obsolete_field": "should_be_removed",
            "another_old_field": 999,
        }

        # Insert old config directly into database
        old_config = DynamicConfig(
            module_name="simple",
            config_data=old_data,
            config_schema_version="old_version_456",
        )
        test_db_session.add(old_config)
        await test_db_session.commit()

        # Initialize should trigger migration
        await manager.initialize_all_configs()

        # Check migrated config
        config = manager.get_config("simple")
        config_dict = config.model_dump()

        # Valid fields should be preserved
        assert config_dict["name"] == "test_name"
        assert config_dict["enabled"] is True
        assert config_dict["count"] == 5

        # Obsolete fields should be removed
        assert "obsolete_field" not in config_dict
        assert "another_old_field" not in config_dict

    @pytest.mark.asyncio
    async def test_nested_config_migration(self, test_config_manager, test_db_session):
        """Test migration works with nested configurations."""
        manager = test_config_manager

        # Create config data with incomplete nested structure
        old_data = {
            "simple_field": "custom_value",
            "nested": {
                "value": "custom_nested",
                "obsolete_nested_field": "remove_me",
                # missing 'number' and 'deprecated_nested'
            },
            "items": [
                {
                    "name": "item1",
                    "old_item_field": "remove_this",
                    # missing 'priority' and 'deprecated_item'
                }
            ],
            "tags": ["custom_tag"],
            "old_top_level": "remove_me_too",
            # missing 'deprecated_field'
        }

        # Insert old config
        old_config = DynamicConfig(
            module_name="complex",
            config_data=old_data,
            config_schema_version="old_nested_version",
        )
        test_db_session.add(old_config)
        await test_db_session.commit()

        # Initialize should trigger migration
        await manager.initialize_all_configs()

        # Check migrated config
        config = manager.get_config("complex")
        config_dict = config.model_dump()

        # Top level fields
        assert config_dict["simple_field"] == "custom_value"  # preserved
        assert config_dict["deprecated_field"] == "deprecated_value"  # added default
        assert "old_top_level" not in config_dict  # removed

        # Nested structure
        nested = config_dict["nested"]
        assert nested["value"] == "custom_nested"  # preserved
        assert nested["number"] == 42  # added default
        assert nested["deprecated_nested"] == "old_nested_value"  # added default
        assert "obsolete_nested_field" not in nested  # removed

        # List items
        assert len(config_dict["items"]) == 1
        item = config_dict["items"][0]
        assert item["name"] == "item1"  # preserved
        assert item["priority"] == 1  # added default
        assert item["deprecated_item"] == "old_item"  # added default
        assert "old_item_field" not in item  # removed

        # Regular list preserved
        assert config_dict["tags"] == ["custom_tag"]

    @pytest.mark.asyncio
    async def test_update_config(self, test_config_manager):
        """Test updating configuration."""
        manager = test_config_manager
        await manager.initialize_all_configs()

        # Update simple config
        new_data = {"name": "updated_name", "enabled": False, "count": 99}

        updated_config = await manager.update_config("simple", new_data)

        # Verify update
        assert updated_config.name == "updated_name"
        assert updated_config.enabled is False
        assert updated_config.count == 99

        # Verify memory cache is updated
        cached_config = manager.get_config("simple")
        assert cached_config.name == "updated_name"
        assert cached_config.enabled is False
        assert cached_config.count == 99

    @pytest.mark.asyncio
    async def test_reset_config(self, test_config_manager):
        """Test resetting configuration to defaults."""
        manager = test_config_manager
        await manager.initialize_all_configs()

        # First update config
        await manager.update_config("simple", {"name": "custom", "count": 999})

        # Verify update
        config = manager.get_config("simple")
        assert config.name == "custom"
        assert config.count == 999

        # Reset to defaults
        reset_config = await manager.reset_config("simple")

        # Verify reset
        assert reset_config.name == "simple_test"  # back to default
        assert reset_config.enabled is True  # back to default
        assert reset_config.count == 10  # back to default

    @pytest.mark.asyncio
    async def test_complex_config_update_with_nested(self, test_config_manager):
        """Test updating complex configuration with nested structures."""
        manager = test_config_manager
        await manager.initialize_all_configs()

        # Update complex config with nested data
        new_data = {
            "simple_field": "updated_simple",
            "nested": {
                "value": "updated_nested",
                "number": 999,
                "deprecated_nested": "updated_deprecated",
            },
            "items": [
                {
                    "name": "new_item1",
                    "priority": 5,
                    "deprecated_item": "new_deprecated",
                },
                {
                    "name": "new_item2",
                    "priority": 10,
                    "deprecated_item": "another_deprecated",
                },
            ],
            "tags": ["tag1", "tag2", "tag3"],
            "deprecated_field": "updated_top_deprecated",
        }

        updated_config = await manager.update_config("complex", new_data)

        # Verify all nested updates
        assert updated_config.simple_field == "updated_simple"
        assert updated_config.nested.value == "updated_nested"
        assert updated_config.nested.number == 999
        assert updated_config.nested.deprecated_nested == "updated_deprecated"

        assert len(updated_config.items) == 2
        assert updated_config.items[0].name == "new_item1"
        assert updated_config.items[0].priority == 5
        assert updated_config.items[1].name == "new_item2"
        assert updated_config.items[1].priority == 10

        assert updated_config.tags == ["tag1", "tag2", "tag3"]
        assert updated_config.deprecated_field == "updated_top_deprecated"


class TestConfigProxy:
    """Test the ConfigProxy functionality."""

    @pytest.mark.asyncio
    async def test_config_proxy_access(self, test_config_manager):
        """Test ConfigProxy provides type-safe access to configurations."""
        from app.dynamic_config import ConfigProxy

        manager = test_config_manager
        await manager.initialize_all_configs()

        # Create proxy
        proxy = ConfigProxy(manager)

        # Test attribute access
        simple_config = cast(SimpleTestConfig, proxy.simple)
        assert simple_config.name == "simple_test"
        assert simple_config.enabled is True

        complex_config = cast(ComplexTestConfig, proxy.complex)
        assert complex_config.simple_field == "test_value"
        assert complex_config.nested.value == "nested_default"

    @pytest.mark.asyncio
    async def test_config_proxy_error_handling(self, test_config_manager):
        """Test ConfigProxy error handling for unknown modules."""
        from app.dynamic_config import ConfigProxy

        manager = test_config_manager
        await manager.initialize_all_configs()

        proxy = ConfigProxy(manager)

        # Test accessing unknown module
        with pytest.raises(AttributeError, match="not available"):
            _ = proxy.unknown_module

    @pytest.mark.asyncio
    async def test_config_proxy_uninitialized_manager(self):
        """Test ConfigProxy with uninitialized manager."""
        from app.dynamic_config import ConfigProxy

        # Create uninitialized manager
        manager = ConfigManager()
        manager.register_config("test", SimpleTestConfig)

        proxy = ConfigProxy(manager)

        # Should raise AttributeError for uninitialized manager
        with pytest.raises(AttributeError, match="not available"):
            _ = proxy.test


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
