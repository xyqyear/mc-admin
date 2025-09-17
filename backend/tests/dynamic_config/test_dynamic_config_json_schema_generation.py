"""
Tests for JSON Schema generation functionality in BaseConfigSchema.
"""

import json
from typing import Annotated, List, Literal, Optional, Union

from pydantic import Field

from app.dynamic_config.schemas import BaseConfigSchema


# Test schemas covering all requirements
class NestedConfig(BaseConfigSchema):
    """Nested configuration for testing."""

    nested_string: str = Field(
        default="nested_default", description="A nested string value"
    )
    nested_number: int = Field(default=42, description="A nested number")


class ListItemConfig(BaseConfigSchema):
    """Configuration used in lists."""

    item_name: str = Field(default="item", description="Name of the item")
    item_value: int = Field(default=1, description="Value of the item")


class ComprehensiveTestConfig(BaseConfigSchema):
    """Comprehensive test configuration covering all requirements."""

    # Basic field types
    string_field: str = Field(default="test_string", description="A string field")
    int_field: int = Field(default=123, description="An integer field")
    float_field: float = Field(default=3.14, description="A float field")
    bool_field: bool = Field(default=True, description="A boolean field")

    # Optional fields
    optional_string: Optional[str] = Field(
        default=None, description="An optional string"
    )
    optional_int: Optional[int] = Field(default=None, description="An optional integer")

    # Required fields (no default)
    required_field: str = Field(description="A required string field")

    # Literal fields
    status: Literal["active", "inactive", "pending"] = Field(
        default="active", description="Status with limited values"
    )
    priority: Literal[1, 2, 3] = Field(default=1, description="Priority level")

    # Union types
    union_field: Union[str, int] = Field(
        default="default", description="A union of string or int"
    )
    union_type_field: str | int = Field(
        default="default", description="A union of string or int"
    )

    complex_union: Union[str, int, bool] = Field(
        default=True, description="A complex union type"
    )

    # List fields
    string_list: List[str] = Field(default=[], description="A list of strings")
    int_list: List[int] = Field(default=[1, 2, 3], description="A list of integers")

    # Nested object
    nested_config: NestedConfig = Field(
        default=NestedConfig(), description="A nested configuration object"
    )

    # List of nested objects
    config_list: List[ListItemConfig] = Field(
        default=[], description="A list of configuration objects"
    )

    # Complex nested union
    nested_union: Union[NestedConfig, str] = Field(
        default="simple_string", description="Union of nested config or string"
    )


class SimpleConfig(BaseConfigSchema):
    """Simple configuration for basic testing."""

    name: str = Field(default="simple", description="Simple name field")
    enabled: bool = Field(default=True, description="Whether enabled")


class TestJSONSchemaGeneration:
    """Test cases for JSON Schema generation."""

    def test_basic_field_types(self):
        """Test basic Python type to JSON Schema conversion."""
        schema = SimpleConfig.get_json_schema()

        assert schema["$schema"] == "http://json-schema.org/draft-07/schema#"
        assert schema["title"] == "SimpleConfig"
        assert schema["type"] == "object"

        properties = schema["properties"]
        assert properties["name"]["type"] == "string"
        assert properties["name"]["default"] == "simple"
        assert properties["name"]["description"] == "Simple name field"

        assert properties["enabled"]["type"] == "boolean"
        assert properties["enabled"]["default"] is True

    def test_comprehensive_schema_generation(self):
        """Test comprehensive schema with all supported features."""
        schema = ComprehensiveTestConfig.get_json_schema()

        # Check basic structure
        assert schema["$schema"] == "http://json-schema.org/draft-07/schema#"
        assert schema["title"] == "ComprehensiveTestConfig"
        assert schema["type"] == "object"
        assert "properties" in schema
        assert "required" in schema
        assert "definitions" in schema

        properties = schema["properties"]

        # Test basic types
        assert properties["string_field"]["type"] == "string"
        assert properties["int_field"]["type"] == "integer"
        assert properties["float_field"]["type"] == "number"
        assert properties["bool_field"]["type"] == "boolean"

        # Test defaults
        assert properties["string_field"]["default"] == "test_string"
        assert properties["int_field"]["default"] == 123
        assert properties["float_field"]["default"] == 3.14
        assert properties["bool_field"]["default"] is True

        # Test descriptions
        assert properties["string_field"]["description"] == "A string field"
        assert properties["int_field"]["description"] == "An integer field"

        # Test required fields
        assert "required_field" in schema["required"]
        assert "string_field" not in schema.get(
            "required", []
        )  # Has default, not required

    def test_optional_fields(self):
        """Test optional field handling."""
        schema = ComprehensiveTestConfig.get_json_schema()
        properties = schema["properties"]

        # Optional fields should be treated as the base type, not union
        assert properties["optional_string"]["type"] == "string"
        assert properties["optional_int"]["type"] == "integer"
        assert properties["optional_string"]["default"] is None
        assert properties["optional_int"]["default"] is None

    def test_literal_types(self):
        """Test Literal type handling."""
        schema = ComprehensiveTestConfig.get_json_schema()
        properties = schema["properties"]

        # String literal
        status_schema = properties["status"]
        assert status_schema["type"] == "string"
        assert status_schema["enum"] == ["active", "inactive", "pending"]
        assert status_schema["default"] == "active"

        # Integer literal
        priority_schema = properties["priority"]
        assert priority_schema["type"] == "number"
        assert priority_schema["enum"] == [1, 2, 3]
        assert priority_schema["default"] == 1

    def test_union_types(self):
        """Test Union type handling."""
        schema = ComprehensiveTestConfig.get_json_schema()
        properties = schema["properties"]

        # Simple union
        union_schema = properties["union_field"]
        assert "oneOf" in union_schema
        union_types = union_schema["oneOf"]
        assert {"type": "string"} in union_types
        assert {"type": "integer"} in union_types
        assert "default" not in union_schema

        # Simple union with types.UnionType
        union_type_schema = properties["union_type_field"]
        assert "oneOf" in union_type_schema
        union_type_options = union_type_schema["oneOf"]
        assert {"type": "string"} in union_type_options
        assert {"type": "integer"} in union_type_options
        assert "default" not in union_type_schema

        # Complex union
        complex_union_schema = properties["complex_union"]
        assert "oneOf" in complex_union_schema
        complex_types = complex_union_schema["oneOf"]
        assert {"type": "string"} in complex_types
        assert {"type": "integer"} in complex_types
        assert {"type": "boolean"} in complex_types

    def test_list_types(self):
        """Test List type handling."""
        schema = ComprehensiveTestConfig.get_json_schema()
        properties = schema["properties"]

        # List of strings
        string_list_schema = properties["string_list"]
        assert string_list_schema["type"] == "array"
        assert string_list_schema["items"]["type"] == "string"
        assert string_list_schema["default"] == []

        # List of integers with default values
        int_list_schema = properties["int_list"]
        assert int_list_schema["type"] == "array"
        assert int_list_schema["items"]["type"] == "integer"
        assert int_list_schema["default"] == [1, 2, 3]

    def test_nested_objects(self):
        """Test nested object handling."""
        schema = ComprehensiveTestConfig.get_json_schema()
        properties = schema["properties"]
        definitions = schema["definitions"]

        # Nested config reference
        nested_schema = properties["nested_config"]
        assert nested_schema["$ref"] == "#/definitions/NestedConfig"

        # Check nested definition exists
        assert "NestedConfig" in definitions
        nested_def = definitions["NestedConfig"]
        assert nested_def["type"] == "object"
        assert "properties" in nested_def

        nested_props = nested_def["properties"]
        assert nested_props["nested_string"]["type"] == "string"
        assert nested_props["nested_string"]["default"] == "nested_default"
        assert nested_props["nested_number"]["type"] == "integer"
        assert nested_props["nested_number"]["default"] == 42

    def test_list_of_nested_objects(self):
        """Test list of nested objects."""
        schema = ComprehensiveTestConfig.get_json_schema()
        properties = schema["properties"]
        definitions = schema["definitions"]

        # List of nested configs
        config_list_schema = properties["config_list"]
        assert config_list_schema["type"] == "array"
        assert config_list_schema["items"]["$ref"] == "#/definitions/ListItemConfig"

        # Check nested definition exists
        assert "ListItemConfig" in definitions
        list_item_def = definitions["ListItemConfig"]
        assert list_item_def["type"] == "object"

        list_props = list_item_def["properties"]
        assert list_props["item_name"]["type"] == "string"
        assert list_props["item_name"]["default"] == "item"
        assert list_props["item_value"]["type"] == "integer"
        assert list_props["item_value"]["default"] == 1

    def test_nested_union_types(self):
        """Test union types with nested objects."""
        schema = ComprehensiveTestConfig.get_json_schema()
        properties = schema["properties"]

        # Union of nested object and string
        nested_union_schema = properties["nested_union"]
        assert "oneOf" in nested_union_schema
        union_types = nested_union_schema["oneOf"]

        # Should contain reference to nested config and string type
        refs_and_types = [item.get("$ref") or item.get("type") for item in union_types]
        assert "#/definitions/NestedConfig" in refs_and_types
        assert "string" in refs_and_types

    def test_json_serializable_output(self):
        """Test that the generated schema is JSON serializable."""
        schema = ComprehensiveTestConfig.get_json_schema()

        # Should not raise an exception
        json_string = json.dumps(schema, indent=2)

        # Should be able to parse back
        parsed_schema = json.loads(json_string)
        assert parsed_schema == schema

    def test_schema_validation_structure(self):
        """Test that generated schema has proper JSON Schema structure."""
        schema = ComprehensiveTestConfig.get_json_schema()

        # Required top-level fields
        assert "$schema" in schema
        assert "title" in schema
        assert "type" in schema
        assert "properties" in schema

        # Schema version should be valid
        assert schema["$schema"] == "http://json-schema.org/draft-07/schema#"

        # Type should be object for config schemas
        assert schema["type"] == "object"

        # Properties should be a dictionary
        assert isinstance(schema["properties"], dict)

        # If required exists, it should be a list
        if "required" in schema:
            assert isinstance(schema["required"], list)

        # If definitions exist, it should be a dictionary
        if "definitions" in schema:
            assert isinstance(schema["definitions"], dict)

    def test_empty_schema(self):
        """Test schema generation for empty configuration."""

        class EmptyConfig(BaseConfigSchema):
            """Empty configuration."""

            pass

        schema = EmptyConfig.get_json_schema()

        assert schema["$schema"] == "http://json-schema.org/draft-07/schema#"
        assert schema["title"] == "EmptyConfig"
        assert schema["type"] == "object"
        assert schema["properties"] == {}
        assert "required" not in schema or schema["required"] == []
        assert "definitions" not in schema or schema["definitions"] == {}

    def test_complex_nested_scenario(self):
        """Test complex nested scenario similar to DNS configuration."""

        class ProviderParams(BaseConfigSchema):
            api_key: str = Field(default="key", description="API key")
            region: str = Field(default="us-east-1", description="Region")

        class ProviderConfig(BaseConfigSchema):
            type: Literal["aws", "gcp", "azure"] = Field(
                default="aws", description="Provider type"
            )
            params: ProviderParams = Field(
                default=ProviderParams(), description="Provider parameters"
            )

        class ComplexConfig(BaseConfigSchema):
            enabled: bool = Field(default=False, description="Whether enabled")
            providers: List[ProviderConfig] = Field(
                default=[], description="List of providers"
            )
            fallback: Union[ProviderConfig, str] = Field(
                default="none", description="Fallback configuration"
            )

        schema = ComplexConfig.get_json_schema()

        # Basic structure
        assert schema["title"] == "ComplexConfig"
        assert "definitions" in schema

        # Check nested definitions exist
        definitions = schema["definitions"]
        assert "ProviderConfig" in definitions
        assert "ProviderParams" in definitions

        # Check provider params
        provider_params = definitions["ProviderParams"]
        assert provider_params["properties"]["api_key"]["type"] == "string"
        assert provider_params["properties"]["region"]["type"] == "string"

        # Check provider config with literal
        provider_config = definitions["ProviderConfig"]
        type_field = provider_config["properties"]["type"]
        assert type_field["type"] == "string"
        assert type_field["enum"] == ["aws", "gcp", "azure"]

        # Check main properties
        properties = schema["properties"]

        # List of providers
        providers_schema = properties["providers"]
        assert providers_schema["type"] == "array"
        assert providers_schema["items"]["$ref"] == "#/definitions/ProviderConfig"

        # Union fallback - should NOT have discriminator (mixed BaseConfig and string)
        fallback_schema = properties["fallback"]
        assert "oneOf" in fallback_schema
        assert (
            "discriminator" not in fallback_schema
        )  # Mixed union should not have discriminator
        union_options = fallback_schema["oneOf"]
        refs_and_types = [
            option.get("$ref") or option.get("type") for option in union_options
        ]
        assert "#/definitions/ProviderConfig" in refs_and_types
        assert "string" in refs_and_types

    def test_discriminated_union_schema_generation(self):
        """Test discriminated union schema generation with proper discriminator field."""

        class DatabaseConfig(BaseConfigSchema):
            type: Annotated[Literal["database"], Field(description="Database type")] = (
                "database"
            )
            host: Annotated[str, Field(description="Database host")] = "localhost"
            port: Annotated[int, Field(description="Database port")] = 5432

        class FileConfig(BaseConfigSchema):
            type: Annotated[Literal["file"], Field(description="File type")] = "file"
            path: Annotated[str, Field(description="File path")] = "/tmp/data"
            format: Annotated[
                Literal["json", "yaml"], Field(description="File format")
            ] = "json"

        class CacheConfig(BaseConfigSchema):
            type: Annotated[Literal["cache"], Field(description="Cache type")] = "cache"
            ttl: Annotated[int, Field(description="Time to live")] = 3600

        class ConfigWithDiscriminatedUnion(BaseConfigSchema):
            name: Annotated[str, Field(description="Configuration name")] = "config"
            storage: Annotated[
                Union[DatabaseConfig, FileConfig, CacheConfig],
                Field(description="Storage configuration", discriminator="type"),
            ] = DatabaseConfig()

        schema = ConfigWithDiscriminatedUnion.get_json_schema()

        # Basic structure checks
        assert schema["title"] == "ConfigWithDiscriminatedUnion"
        assert "definitions" in schema
        assert "properties" in schema

        # Check that all config types are in definitions
        definitions = schema["definitions"]
        assert "DatabaseConfig" in definitions
        assert "FileConfig" in definitions
        assert "CacheConfig" in definitions

        # Check storage field has oneOf with discriminator
        properties = schema["properties"]
        storage_schema = properties["storage"]

        assert "oneOf" in storage_schema
        assert "discriminator" in storage_schema
        assert storage_schema["discriminator"]["propertyName"] == "type"

        # Check oneOf contains correct references
        one_of_options = storage_schema["oneOf"]
        assert len(one_of_options) == 3

        refs = [option["$ref"] for option in one_of_options]
        assert "#/definitions/DatabaseConfig" in refs
        assert "#/definitions/FileConfig" in refs
        assert "#/definitions/CacheConfig" in refs

        # Verify each config type has the required type field
        for config_name in ["DatabaseConfig", "FileConfig", "CacheConfig"]:
            config_def = definitions[config_name]
            assert "type" in config_def["properties"]
            type_field = config_def["properties"]["type"]
            assert type_field["type"] == "string"
            assert "enum" in type_field

        # Verify specific type field values
        db_type = definitions["DatabaseConfig"]["properties"]["type"]
        assert db_type["enum"] == ["database"]

        file_type = definitions["FileConfig"]["properties"]["type"]
        assert file_type["enum"] == ["file"]

        cache_type = definitions["CacheConfig"]["properties"]["type"]
        assert cache_type["enum"] == ["cache"]

    def test_non_discriminated_union_schema_generation(self):
        """Test that non-BaseConfigSchema unions do NOT get discriminator."""

        class ConfigWithRegularUnion(BaseConfigSchema):
            name: str = Field(default="config", description="Configuration name")
            value: Union[str, int, bool] = Field(
                default="test", description="Value union"
            )
            optional_field: Optional[str] = Field(
                default=None, description="Optional field"
            )

        schema = ConfigWithRegularUnion.get_json_schema()

        properties = schema["properties"]

        # Regular union should have oneOf but NO discriminator
        value_schema = properties["value"]
        assert "oneOf" in value_schema
        assert "discriminator" not in value_schema

        # Check oneOf types
        one_of_options = value_schema["oneOf"]
        types = [option["type"] for option in one_of_options]
        assert "string" in types
        assert "integer" in types
        assert "boolean" in types

        # Optional field should not be a union at all
        optional_schema = properties["optional_field"]
        assert "oneOf" not in optional_schema
        assert "discriminator" not in optional_schema
        assert optional_schema["type"] == "string"

    def test_annotated_list_with_discriminated_union_schema(self):
        """Test Annotated list with discriminated union items."""

        class ItemA(BaseConfigSchema):
            type: Annotated[Literal["item_a"], Field(description="Item type A")] = (
                "item_a"
            )
            value_a: Annotated[str, Field(description="Value A")] = "default_a"

        class ItemB(BaseConfigSchema):
            type: Annotated[Literal["item_b"], Field(description="Item type B")] = (
                "item_b"
            )
            value_b: Annotated[int, Field(description="Value B")] = 42

        class ConfigWithAnnotatedList(BaseConfigSchema):
            items: Annotated[
                list[Annotated[Union[ItemA, ItemB], Field(discriminator="type")]],
                Field(description="List of discriminated items"),
            ] = []

        schema = ConfigWithAnnotatedList.get_json_schema()

        # Check basic structure
        assert schema["title"] == "ConfigWithAnnotatedList"
        assert "properties" in schema
        assert "definitions" in schema

        # Check items array
        properties = schema["properties"]
        items_schema = properties["items"]
        assert items_schema["type"] == "array"
        assert "items" in items_schema

        # Check array items have discriminated union
        array_items_schema = items_schema["items"]
        assert "oneOf" in array_items_schema
        assert "discriminator" in array_items_schema
        assert array_items_schema["discriminator"]["propertyName"] == "type"

        # Check definitions
        definitions = schema["definitions"]
        assert "ItemA" in definitions
        assert "ItemB" in definitions

    def test_dns_config_style_schema(self):
        """Test DNS-style configuration schema generation."""

        class ProviderA(BaseConfigSchema):
            type: Annotated[Literal["provider_a"], Field(description="Provider A")] = (
                "provider_a"
            )
            api_key: Annotated[str, Field(description="API key")] = "key"

        class ProviderB(BaseConfigSchema):
            type: Annotated[Literal["provider_b"], Field(description="Provider B")] = (
                "provider_b"
            )
            token: Annotated[str, Field(description="Token")] = "token"

        class DNSStyleConfig(BaseConfigSchema):
            enabled: Annotated[bool, Field(description="Enable DNS")] = True
            provider: Annotated[
                ProviderA | ProviderB,
                Field(description="DNS Provider", discriminator="type"),
            ] = ProviderA()
            servers: Annotated[
                list[
                    Annotated[Union[ProviderA, ProviderB], Field(discriminator="type")]
                ],
                Field(description="List of DNS servers"),
            ] = []

        schema = DNSStyleConfig.get_json_schema()

        # Check main structure
        assert schema["title"] == "DNSStyleConfig"
        properties = schema["properties"]

        # Check provider field has discriminator
        provider_schema = properties["provider"]
        assert "oneOf" in provider_schema
        assert "discriminator" in provider_schema
        assert provider_schema["discriminator"]["propertyName"] == "type"

        # Check servers list has discriminated union items
        servers_schema = properties["servers"]
        assert servers_schema["type"] == "array"
        array_items = servers_schema["items"]
        assert "oneOf" in array_items
        assert "discriminator" in array_items
        assert array_items["discriminator"]["propertyName"] == "type"


if __name__ == "__main__":
    # Run a quick test to see the generated schema
    schema = ComprehensiveTestConfig.get_json_schema()
    print("Generated JSON Schema:")
    print(json.dumps(schema, indent=2))
