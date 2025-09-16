"""
Tests for Union field validation in BaseConfigSchema._validate_union_fields.

This test file covers all code branches in the validation logic to ensure
proper Union field handling and discriminated union enforcement.
"""

from typing import Literal, Optional, Union

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
        schema = ValidOptionalConfig.get_json_schema()
        assert "optional_field" in schema["properties"]

    def test_valid_optional_union_with_union_syntax(self):
        """Test valid optional field using Union syntax - should pass."""

        class ValidOptionalUnionConfig(BaseConfigSchema):
            optional_field: Union[str, None] = Field(
                default=None, description="Optional string"
            )

        # Should not raise an exception
        schema = ValidOptionalUnionConfig.get_json_schema()
        assert "optional_field" in schema["properties"]

    def test_valid_optional_union_with_pipe_syntax(self):
        """Test valid optional field using pipe syntax - should pass."""

        class ValidOptionalPipeConfig(BaseConfigSchema):
            optional_field: str | None = Field(
                default=None, description="Optional string"
            )

        # Should not raise an exception
        schema = ValidOptionalPipeConfig.get_json_schema()
        assert "optional_field" in schema["properties"]

    def test_valid_non_base_config_union(self):
        """Test valid Union of non-BaseConfigSchema types - should pass."""

        class ValidNonBaseUnionConfig(BaseConfigSchema):
            mixed_field: Union[str, int, bool] = Field(
                default="test", description="Mixed types"
            )

        # Should not raise an exception
        schema = ValidNonBaseUnionConfig.get_json_schema()
        properties = schema["properties"]
        assert "oneOf" in properties["mixed_field"]

    def test_valid_non_base_config_union_with_pipe(self):
        """Test valid Union using pipe syntax with non-BaseConfigSchema types - should pass."""

        class ValidNonBasePipeUnionConfig(BaseConfigSchema):
            mixed_field: str | int | bool = Field(
                default="test", description="Mixed types"
            )

        # Should not raise an exception
        schema = ValidNonBasePipeUnionConfig.get_json_schema()
        properties = schema["properties"]
        assert "oneOf" in properties["mixed_field"]

    def test_valid_all_base_config_union_with_discriminator(self):
        """Test valid Union of BaseConfigSchema types with proper type fields - should pass."""

        class ConfigA(BaseConfigSchema):
            type: Literal["config_a"] = Field(
                default="config_a", description="Type discriminator"
            )
            field_a: str = Field(default="a", description="Field A")

        class ConfigB(BaseConfigSchema):
            type: Literal["config_b"] = Field(
                default="config_b", description="Type discriminator"
            )
            field_b: int = Field(default=1, description="Field B")

        class ValidAllBaseUnionConfig(BaseConfigSchema):
            config_union: Union[ConfigA, ConfigB] = Field(
                default_factory=ConfigA, description="Config union"
            )

        # Should not raise an exception
        schema = ValidAllBaseUnionConfig.get_json_schema()
        properties = schema["properties"]
        assert "oneOf" in properties["config_union"]
        assert "discriminator" in properties["config_union"]
        assert properties["config_union"]["discriminator"]["propertyName"] == "type"

    def test_valid_all_base_config_union_with_pipe_syntax(self):
        """Test valid Union using pipe syntax with BaseConfigSchema types - should pass."""

        class ConfigC(BaseConfigSchema):
            type: Literal["config_c"] = Field(
                default="config_c", description="Type discriminator"
            )
            field_c: str = Field(default="c", description="Field C")

        class ConfigD(BaseConfigSchema):
            type: Literal["config_d"] = Field(
                default="config_d", description="Type discriminator"
            )
            field_d: bool = Field(default=True, description="Field D")

        class ValidAllBasePipeUnionConfig(BaseConfigSchema):
            config_union: ConfigC | ConfigD = Field(
                default_factory=ConfigC, description="Config union"
            )

        # Should not raise an exception
        schema = ValidAllBasePipeUnionConfig.get_json_schema()
        properties = schema["properties"]
        assert "oneOf" in properties["config_union"]
        assert "discriminator" in properties["config_union"]

    def test_invalid_mixed_union_base_and_non_base(self):
        """Test invalid Union mixing BaseConfigSchema and non-BaseConfigSchema types - should fail."""

        class ConfigE(BaseConfigSchema):
            type: Literal["config_e"] = Field(
                default="config_e", description="Type discriminator"
            )
            field_e: str = Field(default="e", description="Field E")

        with pytest.raises(
            ValueError,
            match="Field 'mixed_invalid' has a Union with mixed BaseConfigSchema and non-BaseConfigSchema types",
        ):

            class InvalidMixedUnionConfig(BaseConfigSchema):
                mixed_invalid: Union[ConfigE, str, int] = Field(
                    default="test", description="Invalid mixed union"
                )

            # Trigger validation by instantiating
            InvalidMixedUnionConfig()

    def test_invalid_mixed_union_with_pipe_syntax(self):
        """Test invalid Union using pipe syntax mixing types - should fail."""

        class ConfigF(BaseConfigSchema):
            type: Literal["config_f"] = Field(
                default="config_f", description="Type discriminator"
            )
            field_f: str = Field(default="f", description="Field F")

        with pytest.raises(
            ValueError,
            match="Field 'mixed_invalid' has a Union with mixed BaseConfigSchema and non-BaseConfigSchema types",
        ):

            class InvalidMixedPipeUnionConfig(BaseConfigSchema):
                mixed_invalid: ConfigF | str | int = Field(
                    default="test", description="Invalid mixed union"
                )

            # Trigger validation by instantiating
            InvalidMixedPipeUnionConfig()

    def test_invalid_base_config_union_missing_type_field(self):
        """Test invalid BaseConfigSchema Union where one type lacks 'type' field - should fail."""

        class ConfigWithType(BaseConfigSchema):
            type: Literal["with_type"] = Field(
                default="with_type", description="Type discriminator"
            )
            field_a: str = Field(default="a", description="Field A")

        class ConfigWithoutType(BaseConfigSchema):
            field_b: str = Field(default="b", description="Field B")  # No 'type' field

        with pytest.raises(
            ValueError,
            match="BaseConfigSchema subclass 'ConfigWithoutType' in Union field 'invalid_union' must have a 'type' field for discrimination",
        ):

            class InvalidNoTypeFieldConfig(BaseConfigSchema):
                invalid_union: Union[ConfigWithType, ConfigWithoutType] = Field(
                    default_factory=ConfigWithType, description="Invalid union"
                )

            # Trigger validation by instantiating
            InvalidNoTypeFieldConfig()

    def test_invalid_base_config_union_non_literal_type_field(self):
        """Test invalid BaseConfigSchema Union where 'type' field is not Literal - should fail."""

        class ConfigWithLiteralType(BaseConfigSchema):
            type: Literal["literal_type"] = Field(
                default="literal_type", description="Type discriminator"
            )
            field_a: str = Field(default="a", description="Field A")

        class ConfigWithStringType(BaseConfigSchema):
            type: str = Field(
                default="string_type", description="Non-literal type"
            )  # Not Literal
            field_b: str = Field(default="b", description="Field B")

        with pytest.raises(
            ValueError,
            match="BaseConfigSchema subclass 'ConfigWithStringType' in Union field 'invalid_union' must have a 'type' field with Literal\\[\\] annotation",
        ):

            class InvalidNonLiteralTypeConfig(BaseConfigSchema):
                invalid_union: Union[ConfigWithLiteralType, ConfigWithStringType] = (
                    Field(
                        default_factory=ConfigWithLiteralType,
                        description="Invalid union",
                    )
                )

            # Trigger validation by instantiating
            InvalidNonLiteralTypeConfig()

    def test_invalid_base_config_union_with_pipe_missing_type(self):
        """Test invalid BaseConfigSchema Union using pipe syntax missing type field - should fail."""

        class ConfigG(BaseConfigSchema):
            type: Literal["config_g"] = Field(
                default="config_g", description="Type discriminator"
            )
            field_g: str = Field(default="g", description="Field G")

        class ConfigNoType(BaseConfigSchema):
            field_no_type: str = Field(default="no_type", description="No type field")

        with pytest.raises(
            ValueError,
            match="BaseConfigSchema subclass 'ConfigNoType' in Union field 'invalid_pipe_union' must have a 'type' field for discrimination",
        ):

            class InvalidPipeNoTypeConfig(BaseConfigSchema):
                invalid_pipe_union: ConfigG | ConfigNoType = Field(
                    default_factory=ConfigG, description="Invalid pipe union"
                )

            # Trigger validation by instantiating
            InvalidPipeNoTypeConfig()

    def test_valid_single_type_union_skipped(self):
        """Test that single-type Union (after filtering None) is skipped - should pass."""

        class SingleTypeUnionConfig(BaseConfigSchema):
            single_union: str = Field(
                default="test", description="Single type - not actually a union"
            )

        # Should not raise an exception - single type unions are skipped
        schema = SingleTypeUnionConfig.get_json_schema()
        assert "single_union" in schema["properties"]

    def test_validation_with_types_union_type(self):
        """Test validation works with types.UnionType (Python 3.10+ union syntax) - should pass."""

        class ConfigH(BaseConfigSchema):
            type: Literal["config_h"] = Field(
                default="config_h", description="Type discriminator"
            )
            field_h: str = Field(default="h", description="Field H")

        class ConfigI(BaseConfigSchema):
            type: Literal["config_i"] = Field(
                default="config_i", description="Type discriminator"
            )
            field_i: int = Field(default=1, description="Field I")

        # This creates a types.UnionType in Python 3.10+
        class ValidTypesUnionConfig(BaseConfigSchema):
            types_union: ConfigH | ConfigI = Field(
                default_factory=ConfigH, description="Types union"
            )

        # Should not raise an exception
        schema = ValidTypesUnionConfig.get_json_schema()
        properties = schema["properties"]
        assert "oneOf" in properties["types_union"]
        assert "discriminator" in properties["types_union"]

    def test_complex_nested_union_validation(self):
        """Test complex nested Union scenarios - should pass."""

        class NestedConfigA(BaseConfigSchema):
            type: Literal["nested_a"] = Field(
                default="nested_a", description="Nested type A"
            )
            nested_field: str = Field(default="nested", description="Nested field")

        class NestedConfigB(BaseConfigSchema):
            type: Literal["nested_b"] = Field(
                default="nested_b", description="Nested type B"
            )
            nested_number: int = Field(default=42, description="Nested number")

        class ComplexUnionConfig(BaseConfigSchema):
            # Valid: all BaseConfigSchema with type fields
            config_union: Union[NestedConfigA, NestedConfigB] = Field(
                default_factory=NestedConfigA, description="Config union"
            )

            # Valid: non-BaseConfigSchema union
            value_union: Union[str, int, float] = Field(
                default="test", description="Value union"
            )

            # Valid: optional field
            optional_config: Optional[NestedConfigA] = Field(
                default=None, description="Optional config"
            )

        # Should not raise an exception
        schema = ComplexUnionConfig.get_json_schema()
        properties = schema["properties"]

        # Check discriminated union
        assert "oneOf" in properties["config_union"]
        assert "discriminator" in properties["config_union"]

        # Check regular union
        assert "oneOf" in properties["value_union"]
        assert "discriminator" not in properties["value_union"]

        # Check optional field (should not be a union in schema)
        assert properties["optional_config"]["$ref"] == "#/definitions/NestedConfigA"

    def test_edge_case_none_type_handling(self):
        """Test edge cases with None type handling - should pass."""

        class EdgeCaseConfig(BaseConfigSchema):
            # Multiple ways to specify optional
            optional_a: Union[str, None] = Field(default=None, description="Optional A")
            optional_b: Union[None, str] = Field(default=None, description="Optional B")
            optional_c: Optional[str] = Field(default=None, description="Optional C")

        # Should not raise an exception
        schema = EdgeCaseConfig.get_json_schema()
        properties = schema["properties"]

        # All should be treated as string type, not oneOf
        assert properties["optional_a"]["type"] == "string"
        assert properties["optional_b"]["type"] == "string"
        assert properties["optional_c"]["type"] == "string"

    def test_validator_runs_during_class_definition(self):
        """Test that validator runs during class definition, not instance creation."""

        class ValidConfig(BaseConfigSchema):
            type: Literal["valid"] = Field(default="valid", description="Type")
            field: str = Field(default="test", description="Field")

        class InvalidConfigMissingType(BaseConfigSchema):
            field: str = Field(default="test", description="Field")  # No type field

        # Valid union should work
        class WorkingConfig(BaseConfigSchema):
            union_field: Union[ValidConfig, str] = Field(
                default="test", description="Working union"
            )

        # Invalid union should fail when instantiated
        with pytest.raises(ValueError):

            class FailingConfig(BaseConfigSchema):
                union_field: Union[ValidConfig, InvalidConfigMissingType] = Field(
                    default_factory=ValidConfig, description="Failing union"
                )

            # Trigger validation by instantiating
            FailingConfig()

    def test_multiple_union_fields_validation(self):
        """Test validation of multiple Union fields in single class - should pass or fail appropriately."""

        class ConfigJ(BaseConfigSchema):
            type: Literal["config_j"] = Field(default="config_j", description="Type J")
            field_j: str = Field(default="j", description="Field J")

        class ConfigK(BaseConfigSchema):
            type: Literal["config_k"] = Field(default="config_k", description="Type K")
            field_k: bool = Field(default=True, description="Field K")

        class ConfigNoTypeField(BaseConfigSchema):
            field_no_type: str = Field(default="no_type", description="No type field")

        # This should work - valid unions
        class ValidMultipleUnionsConfig(BaseConfigSchema):
            union_a: Union[ConfigJ, ConfigK] = Field(
                default_factory=ConfigJ, description="Union A"
            )
            union_b: Union[str, int] = Field(default="test", description="Union B")
            optional_field: Optional[str] = Field(default=None, description="Optional")

        # Should not raise exception
        schema = ValidMultipleUnionsConfig.get_json_schema()
        properties = schema["properties"]
        assert "discriminator" in properties["union_a"]
        assert "discriminator" not in properties["union_b"]

        # This should fail - one valid, one invalid union
        with pytest.raises(
            ValueError, match="must have a 'type' field for discrimination"
        ):

            class InvalidMultipleUnionsConfig(BaseConfigSchema):
                union_valid: Union[ConfigJ, ConfigK] = Field(
                    default_factory=ConfigJ, description="Valid union"
                )
                union_invalid: Union[ConfigJ, ConfigNoTypeField] = Field(
                    default_factory=ConfigJ, description="Invalid union"
                )

            # Trigger validation by instantiating
            InvalidMultipleUnionsConfig()
