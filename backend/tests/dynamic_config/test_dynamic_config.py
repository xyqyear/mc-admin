"""
Unit tests for the dynamic configuration system.
"""

import pytest
from pydantic import Field

from app.dynamic_config import BaseConfigSchema
from app.dynamic_config.manager import ConfigManager
from app.dynamic_config.migration import ConfigMigrator


class TestConfigSchema(BaseConfigSchema):
    """Test configuration schema for unit tests."""

    simple_field: str = Field(
        default="default_value", description="A simple string field"
    )

    number_field: int = Field(default=42, description="A number field")

    deprecated_field: str = Field(
        default="old_value",
        description="A deprecated field",
        deprecated="Use simple_field instead",
    )


class NestedConfigSchema(BaseConfigSchema):
    """Nested configuration schema for testing."""

    nested_value: str = Field(default="nested_default", description="A nested value")

    nested_deprecated: str = Field(
        default="old_nested",
        description="A deprecated nested field",
        deprecated="No longer needed",
    )


class ComplexConfigSchema(BaseConfigSchema):
    """Complex configuration with nested models and lists."""

    name: str = Field(default="test_config", description="Configuration name")

    nested: NestedConfigSchema = Field(description="Nested configuration")

    nested_list: list[NestedConfigSchema] = Field(
        default=[], description="List of nested configurations"
    )


class TestBaseConfigSchema:
    """Test the BaseConfigSchema functionality."""

    def test_schema_version_generation(self):
        """Test that schema version is generated correctly."""
        version = TestConfigSchema.get_schema_version()
        assert isinstance(version, str)
        assert len(version) == 16  # SHA256 hash truncated to 16 chars

    def test_json_schema_generation(self):
        """Test JSON schema generation."""
        json_schema = TestConfigSchema.get_json_schema()

        assert json_schema["$schema"] == "http://json-schema.org/draft-07/schema#"
        assert json_schema["title"] == "TestConfigSchema"
        assert json_schema["type"] == "object"
        assert "properties" in json_schema

        properties = json_schema["properties"]
        assert "simple_field" in properties
        assert properties["simple_field"]["description"] == "A simple string field"
        assert properties["simple_field"]["type"] == "string"
        assert properties["simple_field"]["default"] == "default_value"

    def test_json_schema_default_handling(self):
        """Test new default handling logic with BaseModel instances."""
        from typing import List

        class NestedTestConfig(BaseConfigSchema):
            nested_name: str = Field(default="nested", description="Nested name")
            nested_value: int = Field(default=99, description="Nested value")

        class DefaultTestConfig(BaseConfigSchema):
            # Simple defaults
            simple_str: str = Field(default="test", description="Simple string")
            simple_list: List[str] = Field(
                default=["a", "b"], description="Simple list"
            )

            # Direct BaseModel default
            nested_direct: NestedTestConfig = Field(
                default=NestedTestConfig(nested_name="direct", nested_value=200),
                description="Direct nested",
            )

        schema = DefaultTestConfig.get_json_schema()
        properties = schema["properties"]

        # Test simple defaults work
        assert properties["simple_str"]["default"] == "test"
        assert properties["simple_list"]["default"] == ["a", "b"]

        # Test direct BaseModel default produces dict
        nested_direct_default = properties["nested_direct"]["default"]
        assert isinstance(nested_direct_default, dict)
        assert nested_direct_default["nested_name"] == "direct"
        assert nested_direct_default["nested_value"] == 200

        # Ensure entire schema is JSON serializable
        import json

        json.dumps(schema)  # Should not raise exception


class TestConfigMigrator:
    """Test the ConfigMigrator functionality."""

    def test_create_default_config(self):
        """Test creating default configuration."""
        default_config = ConfigMigrator.create_default_config(TestConfigSchema)

        assert default_config["simple_field"] == "default_value"
        assert default_config["number_field"] == 42
        assert default_config["deprecated_field"] == "old_value"

    def test_migrate_config_same_version(self):
        """Test migration when versions are the same."""
        current_data = {"simple_field": "custom_value", "number_field": 100}

        current_version = TestConfigSchema.get_schema_version()

        migrated_data, messages = ConfigMigrator.migrate_config(
            current_data, TestConfigSchema, current_version
        )

        # Data should be unchanged for same version
        assert migrated_data["simple_field"] == "custom_value"
        assert migrated_data["number_field"] == 100

    def test_migrate_config_missing_fields(self):
        """Test migration adds missing fields with defaults."""
        current_data = {
            "simple_field": "custom_value"
            # missing number_field and deprecated_field
        }

        old_version = "old_version_hash"

        migrated_data, messages = ConfigMigrator.migrate_config(
            current_data, TestConfigSchema, old_version
        )

        # Should add missing fields with defaults via Pydantic validation
        assert migrated_data["simple_field"] == "custom_value"  # preserved
        assert migrated_data["number_field"] == 42  # added default
        assert migrated_data["deprecated_field"] == "old_value"  # added default

        # Should have migration message indicating version change
        assert any("Migrating TestConfigSchema" in msg for msg in messages)

    def test_migrate_config_removes_obsolete_fields(self):
        """Test migration removes fields not in schema via Pydantic validation."""
        current_data = {
            "simple_field": "custom_value",
            "number_field": 100,
            "old_removed_field": "should_be_removed",
            "another_obsolete": "also_removed",
        }

        old_version = "old_version_hash"

        migrated_data, messages = ConfigMigrator.migrate_config(
            current_data, TestConfigSchema, old_version
        )

        # Should keep valid fields
        assert migrated_data["simple_field"] == "custom_value"
        assert migrated_data["number_field"] == 100

        # Should remove obsolete fields via Pydantic validation
        assert "old_removed_field" not in migrated_data
        assert "another_obsolete" not in migrated_data

        # Should have migration message
        assert any("Migrating TestConfigSchema" in msg for msg in messages)

    def test_migrate_nested_config(self):
        """Test migration of nested configuration structures."""
        current_data = {
            "name": "test_config",
            "nested": {
                "nested_value": "custom_nested",
                "old_field": "should_be_removed",
            },
            "nested_list": [{"nested_value": "item1", "old_field": "remove_this"}],
        }

        old_version = "old_version_hash"

        migrated_data, messages = ConfigMigrator.migrate_config(
            current_data, ComplexConfigSchema, old_version
        )

        # Should handle nested migration
        assert migrated_data["nested"]["nested_value"] == "custom_nested"
        assert "old_field" not in migrated_data["nested"]

        # Should handle list item migration
        assert migrated_data["nested_list"][0]["nested_value"] == "item1"
        assert "old_field" not in migrated_data["nested_list"][0]

    def test_validate_config(self):
        """Test configuration validation."""
        valid_data = {"simple_field": "valid_string", "number_field": 123}

        invalid_data = {
            "simple_field": "valid_string",
            "number_field": "not_a_number",  # Invalid type
        }

        # Valid data should pass
        errors = ConfigMigrator.validate_config(valid_data, TestConfigSchema)
        assert len(errors) == 0

        # Invalid data should fail
        errors = ConfigMigrator.validate_config(invalid_data, TestConfigSchema)
        assert len(errors) > 0


class TestConfigManager:
    """Test the ConfigManager functionality."""

    def test_register_config(self):
        """Test configuration registration."""
        manager = ConfigManager()

        # Should register successfully
        manager.register_config("test_module", TestConfigSchema)
        assert "test_module" in manager._schemas

        # Should raise error for duplicate registration
        with pytest.raises(ValueError, match="already registered"):
            manager.register_config("test_module", TestConfigSchema)

        # Should raise error for invalid schema
        with pytest.raises(ValueError, match="must inherit from BaseConfigSchema"):
            manager.register_config("invalid", str)  # type: ignore this is intentional

    def test_get_schema_info(self):
        """Test schema information retrieval."""
        manager = ConfigManager()
        manager.register_config("test_module", TestConfigSchema)

        info = manager.get_schema_info("test_module")

        assert info["module_name"] == "test_module"
        assert info["schema_class"] == "TestConfigSchema"
        assert "version" in info
        assert "json_schema" in info

        # Verify JSON Schema structure
        json_schema = info["json_schema"]
        assert json_schema["$schema"] == "http://json-schema.org/draft-07/schema#"
        assert json_schema["title"] == "TestConfigSchema"
        assert json_schema["type"] == "object"
        assert "properties" in json_schema

        # Check that test fields are present in JSON Schema
        properties = json_schema["properties"]
        assert "simple_field" in properties
        assert "number_field" in properties
        assert "deprecated_field" in properties

        # Should raise error for unknown module
        with pytest.raises(ValueError, match="not registered"):
            manager.get_schema_info("unknown_module")

    def test_get_all_schema_info(self):
        """Test retrieving all schema information."""
        manager = ConfigManager()
        manager.register_config("test1", TestConfigSchema)
        manager.register_config("test2", ComplexConfigSchema)

        all_info = manager.get_all_schema_info()

        assert len(all_info) == 2
        assert "test1" in all_info
        assert "test2" in all_info

    def test_config_access_before_initialization(self):
        """Test that accessing config before initialization raises error."""
        manager = ConfigManager()
        manager.register_config("test_module", TestConfigSchema)

        with pytest.raises(RuntimeError, match="not initialized"):
            manager.get_config("test_module")

        with pytest.raises(RuntimeError, match="not initialized"):
            manager.get_all_configs()
