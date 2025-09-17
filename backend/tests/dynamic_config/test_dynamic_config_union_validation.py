"""
Tests for Union field validation in BaseConfigSchema._validate_union_fields.

This test file covers all code branches in the validation logic to ensure
proper Union field handling and discriminated union enforcement.
"""

from typing import Annotated, Literal, Optional, Union

import pytest
from pydantic import Field

from app.dynamic_config.schemas import BaseConfigSchema


class TestUnionFieldValidation:
    """Test cases for Union field validation in BaseConfigSchema."""

    def test_valid_optional_union_single_type(self):
        """Test valid optional field (Union[Type, None]) - should pass."""

        class ValidOptionalConfig(BaseConfigSchema):
            optional_field: Optional[str] = Field(
                default=None, description="Optional string"
            )

        # Should not raise an exception
        schema = ValidOptionalConfig.model_json_schema()
        assert "optional_field" in schema["properties"]

    def test_valid_optional_union_with_union_syntax(self):
        """Test valid optional field using Union syntax - should pass."""

        class ValidOptionalUnionConfig(BaseConfigSchema):
            optional_field: Union[str, None] = Field(
                default=None, description="Optional string"
            )

        # Should not raise an exception
        schema = ValidOptionalUnionConfig.model_json_schema()
        assert "optional_field" in schema["properties"]

    def test_valid_optional_union_with_pipe_syntax(self):
        """Test valid optional field using pipe syntax - should pass."""

        class ValidOptionalPipeConfig(BaseConfigSchema):
            optional_field: str | None = Field(
                default=None, description="Optional string"
            )

        # Should not raise an exception
        schema = ValidOptionalPipeConfig.model_json_schema()
        assert "optional_field" in schema["properties"]

    def test_valid_non_base_config_union(self):
        """Test valid Union of non-BaseConfigSchema types - should pass."""

        class ValidNonBaseUnionConfig(BaseConfigSchema):
            mixed_field: Union[str, int, bool] = Field(
                default="test", description="Mixed types"
            )

        # Should not raise an exception
        schema = ValidNonBaseUnionConfig.model_json_schema()
        properties = schema["properties"]
        assert "anyOf" in properties["mixed_field"]

    def test_valid_non_base_config_union_with_pipe(self):
        """Test valid Union using pipe syntax with non-BaseConfigSchema types - should pass."""

        class ValidNonBasePipeUnionConfig(BaseConfigSchema):
            mixed_field: str | int | bool = Field(
                default="test", description="Mixed types"
            )

        # Should not raise an exception
        schema = ValidNonBasePipeUnionConfig.model_json_schema()
        properties = schema["properties"]
        assert "anyOf" in properties["mixed_field"]

    def test_valid_all_base_config_union_with_discriminator(self):
        """Test valid Union of BaseConfigSchema types with discriminator - should pass."""

        class ConfigA(BaseConfigSchema):
            type: Annotated[
                Literal["config_a"], Field(description="Type discriminator")
            ] = "config_a"
            field_a: Annotated[str, Field(description="Field A")] = "a"

        class ConfigB(BaseConfigSchema):
            type: Annotated[
                Literal["config_b"], Field(description="Type discriminator")
            ] = "config_b"
            field_b: Annotated[int, Field(description="Field B")] = 1

        class ValidAllBaseUnionConfig(BaseConfigSchema):
            config_union: Annotated[
                Union[ConfigA, ConfigB],
                Field(description="Config union", discriminator="type"),
            ] = ConfigA()

        # Should not raise an exception
        schema = ValidAllBaseUnionConfig.model_json_schema()
        properties = schema["properties"]
        assert "oneOf" in properties["config_union"]
        assert "discriminator" in properties["config_union"]
        assert properties["config_union"]["discriminator"]["propertyName"] == "type"

    def test_valid_all_base_config_union_with_pipe_syntax(self):
        """Test valid Union using pipe syntax with BaseConfigSchema types - should pass."""

        class ConfigC(BaseConfigSchema):
            type: Annotated[
                Literal["config_c"], Field(description="Type discriminator")
            ] = "config_c"
            field_c: Annotated[str, Field(description="Field C")] = "c"

        class ConfigD(BaseConfigSchema):
            type: Annotated[
                Literal["config_d"], Field(description="Type discriminator")
            ] = "config_d"
            field_d: Annotated[bool, Field(description="Field D")] = True

        class ValidAllBasePipeUnionConfig(BaseConfigSchema):
            config_union: Annotated[
                ConfigC | ConfigD,
                Field(description="Config union", discriminator="type"),
            ] = ConfigC()

        # Should not raise an exception
        schema = ValidAllBasePipeUnionConfig.model_json_schema()
        properties = schema["properties"]
        assert "oneOf" in properties["config_union"]
        assert "discriminator" in properties["config_union"]

    def test_invalid_mixed_union_base_and_non_base(self):
        """Test invalid Union mixing BaseConfigSchema and non-BaseConfigSchema types - should pass (no longer invalid)."""

        class ConfigE(BaseConfigSchema):
            type: Annotated[
                Literal["config_e"], Field(description="Type discriminator")
            ] = "config_e"
            field_e: Annotated[str, Field(description="Field E")] = "e"

        # Mixed unions are now allowed - they just don't get discriminators
        class ValidMixedUnionConfig(BaseConfigSchema):
            mixed_union: Annotated[
                Union[ConfigE, str, int],
                Field(description="Mixed union without discriminator"),
            ] = "test"

        # Should not raise an exception
        schema = ValidMixedUnionConfig.model_json_schema()
        properties = schema["properties"]
        assert "anyOf" in properties["mixed_union"]
        # Mixed unions don't get discriminators
        assert "discriminator" not in properties["mixed_union"]

    def test_invalid_mixed_union_with_pipe_syntax(self):
        """Test mixed Union using pipe syntax - should pass (no longer invalid)."""

        class ConfigF(BaseConfigSchema):
            type: Annotated[
                Literal["config_f"], Field(description="Type discriminator")
            ] = "config_f"
            field_f: Annotated[str, Field(description="Field F")] = "f"

        # Mixed unions are now allowed - they just don't get discriminators
        class ValidMixedPipeUnionConfig(BaseConfigSchema):
            mixed_union: Annotated[
                ConfigF | str | int,
                Field(description="Mixed pipe union without discriminator"),
            ] = "test"

        # Should not raise an exception
        schema = ValidMixedPipeUnionConfig.model_json_schema()
        properties = schema["properties"]
        assert "anyOf" in properties["mixed_union"]
        # Mixed unions don't get discriminators
        assert "discriminator" not in properties["mixed_union"]

    def test_invalid_base_config_union_missing_discriminator_field(self):
        """Test invalid BaseConfigSchema Union missing discriminator - should fail."""

        class ConfigA(BaseConfigSchema):
            type: Annotated[
                Literal["config_a"], Field(description="Type discriminator")
            ] = "config_a"
            field_a: Annotated[str, Field(description="Field A")] = "a"

        class ConfigB(BaseConfigSchema):
            type: Annotated[
                Literal["config_b"], Field(description="Type discriminator")
            ] = "config_b"
            field_b: Annotated[str, Field(description="Field B")] = "b"

        with pytest.raises(
            ValueError,
            match="Union field 'invalid_union' with BaseConfigSchema types must have a discriminator field specified",
        ):

            class InvalidNoDiscriminatorConfig(BaseConfigSchema):
                invalid_union: Annotated[
                    Union[ConfigA, ConfigB],
                    Field(description="Invalid union without discriminator"),
                ] = ConfigA()

            # Trigger validation by instantiating
            InvalidNoDiscriminatorConfig()

    def test_valid_base_config_union_with_different_discriminator(self):
        """Test BaseConfigSchema Union with custom discriminator field - should pass."""

        class DatabaseConfig(BaseConfigSchema):
            backend: Annotated[
                Literal["postgres"], Field(description="Backend type")
            ] = "postgres"
            host: Annotated[str, Field(description="Database host")] = "localhost"

        class FileConfig(BaseConfigSchema):
            backend: Annotated[Literal["file"], Field(description="Backend type")] = (
                "file"
            )
            path: Annotated[str, Field(description="File path")] = "/tmp/data"

        class ValidCustomDiscriminatorConfig(BaseConfigSchema):
            storage: Annotated[
                Union[DatabaseConfig, FileConfig],
                Field(description="Storage configuration", discriminator="backend"),
            ] = DatabaseConfig()

        # Should not raise an exception
        schema = ValidCustomDiscriminatorConfig.model_json_schema()
        properties = schema["properties"]
        assert "oneOf" in properties["storage"]
        assert "discriminator" in properties["storage"]
        assert properties["storage"]["discriminator"]["propertyName"] == "backend"

    def test_annotated_list_with_discriminated_union(self):
        """Test Annotated list containing discriminated union - should pass."""

        class ProviderA(BaseConfigSchema):
            type: Annotated[
                Literal["provider_a"], Field(description="Provider type")
            ] = "provider_a"
            config_a: Annotated[str, Field(description="Config A")] = "value_a"

        class ProviderB(BaseConfigSchema):
            type: Annotated[
                Literal["provider_b"], Field(description="Provider type")
            ] = "provider_b"
            config_b: Annotated[int, Field(description="Config B")] = 42

        class ConfigWithAnnotatedList(BaseConfigSchema):
            providers: Annotated[
                list[
                    Annotated[Union[ProviderA, ProviderB], Field(discriminator="type")]
                ],
                Field(description="List of providers"),
            ] = []

        # Should not raise an exception
        schema = ConfigWithAnnotatedList.model_json_schema()
        properties = schema["properties"]
        assert "type" in properties["providers"]
        assert properties["providers"]["type"] == "array"
        assert "items" in properties["providers"]
        items_schema = properties["providers"]["items"]
        assert "oneOf" in items_schema
        assert "discriminator" in items_schema
        assert items_schema["discriminator"]["propertyName"] == "type"

    def test_valid_single_type_union_skipped(self):
        """Test that single-type Union (after filtering None) is skipped - should pass."""

        class SingleTypeUnionConfig(BaseConfigSchema):
            single_union: str = Field(
                default="test", description="Single type - not actually a union"
            )

        # Should not raise an exception - single type unions are skipped
        schema = SingleTypeUnionConfig.model_json_schema()
        assert "single_union" in schema["properties"]

    def test_validation_with_types_union_type(self):
        """Test validation works with types.UnionType (Python 3.10+ union syntax) - should pass."""

        class ConfigH(BaseConfigSchema):
            type: Annotated[
                Literal["config_h"], Field(description="Type discriminator")
            ] = "config_h"
            field_h: Annotated[str, Field(description="Field H")] = "h"

        class ConfigI(BaseConfigSchema):
            type: Annotated[
                Literal["config_i"], Field(description="Type discriminator")
            ] = "config_i"
            field_i: Annotated[int, Field(description="Field I")] = 1

        # This creates a types.UnionType in Python 3.10+
        class ValidTypesUnionConfig(BaseConfigSchema):
            types_union: Annotated[
                ConfigH | ConfigI,
                Field(description="Types union", discriminator="type"),
            ] = ConfigH()

        # Should not raise an exception
        schema = ValidTypesUnionConfig.model_json_schema()
        properties = schema["properties"]
        assert "oneOf" in properties["types_union"]
        assert "discriminator" in properties["types_union"]

    def test_complex_nested_union_validation(self):
        """Test complex nested Union scenarios - should pass."""

        class NestedConfigA(BaseConfigSchema):
            type: Annotated[Literal["nested_a"], Field(description="Nested type A")] = (
                "nested_a"
            )
            nested_field: Annotated[str, Field(description="Nested field")] = "nested"

        class NestedConfigB(BaseConfigSchema):
            type: Annotated[Literal["nested_b"], Field(description="Nested type B")] = (
                "nested_b"
            )
            nested_number: Annotated[int, Field(description="Nested number")] = 42

        class ComplexUnionConfig(BaseConfigSchema):
            # Valid: all BaseConfigSchema with discriminator
            config_union: Annotated[
                Union[NestedConfigA, NestedConfigB],
                Field(description="Config union", discriminator="type"),
            ] = NestedConfigA()

            # Valid: non-BaseConfigSchema union
            value_union: Annotated[
                Union[str, int, float], Field(description="Value union")
            ] = "test"

            # Valid: optional field
            optional_config: Annotated[
                Optional[NestedConfigA], Field(description="Optional config")
            ] = None

        # Should not raise an exception
        schema = ComplexUnionConfig.model_json_schema()
        properties = schema["properties"]

        # Check discriminated union
        assert "oneOf" in properties["config_union"]
        assert "discriminator" in properties["config_union"]

        # Check regular union
        assert "anyOf" in properties["value_union"]
        assert "discriminator" not in properties["value_union"]

    def test_validator_runs_during_class_definition(self):
        """Test that validator runs during class definition, not instance creation."""

        class ValidConfig(BaseConfigSchema):
            type: Literal["valid"] = Field(default="valid", description="Type")
            field: str = Field(default="test", description="Field")

        class InvalidConfigMissingType(BaseConfigSchema):
            field: str = Field(default="test", description="Field")  # No type field

        # This should work - mixed union is allowed
        class WorkingConfig(BaseConfigSchema):
            union_field: Annotated[
                Union[ValidConfig, str],
                Field(description="Working union without discriminator"),
            ] = "test"

        # Should not raise exception for mixed union
        schema = WorkingConfig.model_json_schema()
        assert "anyOf" in schema["properties"]["union_field"]
        assert "discriminator" not in schema["properties"]["union_field"]

        # Invalid union should fail when instantiated
        with pytest.raises(ValueError):

            class FailingConfig(BaseConfigSchema):
                union_field: Annotated[
                    Union[ValidConfig, InvalidConfigMissingType],
                    Field(description="Failing union without discriminator"),
                ] = ValidConfig()

            # Trigger validation by instantiating
            FailingConfig()

    def test_multiple_union_fields_validation(self):
        """Test validation of multiple Union fields in single class - should pass appropriately."""

        class ConfigJ(BaseConfigSchema):
            type: Annotated[Literal["config_j"], Field(description="Type J")] = (
                "config_j"
            )
            field_j: Annotated[str, Field(description="Field J")] = "j"

        class ConfigK(BaseConfigSchema):
            type: Annotated[Literal["config_k"], Field(description="Type K")] = (
                "config_k"
            )
            field_k: Annotated[bool, Field(description="Field K")] = True

        # This should work - valid unions
        class ValidMultipleUnionsConfig(BaseConfigSchema):
            union_a: Annotated[
                Union[ConfigJ, ConfigK],
                Field(description="Union A", discriminator="type"),
            ] = ConfigJ()
            union_b: Annotated[Union[str, int], Field(description="Union B")] = "test"
            optional_field: Annotated[Optional[str], Field(description="Optional")] = (
                None
            )

        # Should not raise exception
        schema = ValidMultipleUnionsConfig.model_json_schema()
        properties = schema["properties"]
        assert "discriminator" in properties["union_a"]
        assert "discriminator" not in properties["union_b"]

        # Test invalid case - union without discriminator
        with pytest.raises(
            ValueError,
            match="Union field 'union_invalid' with BaseConfigSchema types must have a discriminator field specified",
        ):

            class InvalidMultipleUnionsConfig(BaseConfigSchema):
                union_valid: Annotated[
                    Union[ConfigJ, ConfigK],
                    Field(description="Valid union", discriminator="type"),
                ] = ConfigJ()
                union_invalid: Annotated[
                    Union[ConfigJ, ConfigK],
                    Field(description="Invalid union without discriminator"),
                ] = ConfigJ()

            # Trigger validation by instantiating
            InvalidMultipleUnionsConfig()
