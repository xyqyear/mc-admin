"""Unit tests for TemplateManager core business logic."""

import pytest

from app.templates import (
    BoolVariableDefinition,
    EnumVariableDefinition,
    FloatVariableDefinition,
    IntVariableDefinition,
    StringVariableDefinition,
)
from app.templates.manager import TemplateManager


class TestExtractVariables:
    """Test variable extraction from YAML templates."""

    def test_extract_single_variable(self):
        """Test extracting a single variable from YAML."""
        yaml = "container_name: mc-{name}"
        result = TemplateManager.extract_variables_from_yaml(yaml)
        assert result == {"name"}

    def test_extract_multiple_variables(self):
        """Test extracting multiple variables from YAML."""
        yaml = """
        container_name: mc-{name}
        ports:
          - "{game_port}:25565"
          - "{rcon_port}:25575"
        """
        result = TemplateManager.extract_variables_from_yaml(yaml)
        assert result == {"name", "game_port", "rcon_port"}

    def test_extract_no_variables(self):
        """Test extracting from YAML with no variables."""
        yaml = "container_name: mc-server"
        result = TemplateManager.extract_variables_from_yaml(yaml)
        assert result == set()

    def test_extract_duplicate_variables(self):
        """Test that duplicate variables are deduplicated."""
        yaml = "{name} and {name} again"
        result = TemplateManager.extract_variables_from_yaml(yaml)
        assert result == {"name"}


class TestValidateTemplate:
    """Test template validation."""

    def test_validate_success(self):
        """Test validation passes when variables match exactly."""
        yaml = "container_name: mc-{name}\nport: {port}"
        variables = [
            StringVariableDefinition(name="name", display_name="Name"),
            IntVariableDefinition(name="port", display_name="Port"),
        ]
        errors = TemplateManager.validate_template(yaml, variables)
        assert errors == []

    def test_validate_undefined_variable(self):
        """Test validation fails for undefined variables in YAML."""
        yaml = "container_name: mc-{name}\nport: {undefined_var}"
        variables = [
            StringVariableDefinition(name="name", display_name="Name"),
        ]
        errors = TemplateManager.validate_template(yaml, variables)
        assert len(errors) == 1
        assert "YAML 中使用了未定义的变量" in errors[0]
        assert "undefined_var" in errors[0]

    def test_validate_unused_variable(self):
        """Test validation fails for defined but unused variables."""
        yaml = "container_name: mc-{name}"
        variables = [
            StringVariableDefinition(name="name", display_name="Name"),
            IntVariableDefinition(name="unused", display_name="Unused"),
        ]
        errors = TemplateManager.validate_template(yaml, variables)
        assert len(errors) == 1
        assert "已定义但未在 YAML 中使用的变量" in errors[0]
        assert "unused" in errors[0]

    def test_validate_duplicate_variable_names(self):
        """Test validation fails for duplicate variable names."""
        yaml = "container_name: mc-{name}"
        variables = [
            StringVariableDefinition(name="name", display_name="Name 1"),
            StringVariableDefinition(name="name", display_name="Name 2"),
        ]
        errors = TemplateManager.validate_template(yaml, variables)
        assert any("用户变量名重复" in e for e in errors)


class TestRenderYaml:
    """Test YAML rendering with variable substitution."""

    def test_render_success(self):
        """Test successful YAML rendering."""
        yaml = "container_name: mc-{name}\nport: {port}"
        values = {"name": "test-server", "port": 25565}
        result = TemplateManager.render_yaml(yaml, values)
        assert result == "container_name: mc-test-server\nport: 25565"

    def test_render_missing_value(self):
        """Test rendering fails when variable value is missing."""
        yaml = "container_name: mc-{name}\nport: {port}"
        values = {"name": "test-server"}
        with pytest.raises(ValueError) as exc_info:
            TemplateManager.render_yaml(yaml, values)
        assert "port" in str(exc_info.value)
        assert "未提供值" in str(exc_info.value)

    def test_render_boolean_value(self):
        """Test rendering boolean values."""
        yaml = "enabled: {flag}"
        values = {"flag": True}
        result = TemplateManager.render_yaml(yaml, values)
        assert result == "enabled: True"


class TestGenerateJsonSchema:
    """Test JSON Schema generation for rjsf forms."""

    def test_schema_int_variable(self):
        """Test JSON Schema for integer variable."""
        variables = [
            IntVariableDefinition(
                name="port",
                display_name="Port",
                description="Server port",
                default=25565,
                min_value=1024,
                max_value=65535,
            )
        ]
        schema = TemplateManager.generate_json_schema(variables)
        assert schema["type"] == "object"
        assert "port" in schema["properties"]
        prop = schema["properties"]["port"]
        assert prop["type"] == "integer"
        assert prop["title"] == "Port"
        assert prop["minimum"] == 1024
        assert prop["maximum"] == 65535
        assert prop["default"] == 25565
        assert "port" in schema["required"]

    def test_schema_float_variable(self):
        """Test JSON Schema for float variable."""
        variables = [
            FloatVariableDefinition(
                name="ratio", display_name="Ratio", min_value=0.0, max_value=1.0
            )
        ]
        schema = TemplateManager.generate_json_schema(variables)
        prop = schema["properties"]["ratio"]
        assert prop["type"] == "number"
        assert prop["minimum"] == 0.0
        assert prop["maximum"] == 1.0

    def test_schema_string_variable(self):
        """Test JSON Schema for string variable."""
        variables = [
            StringVariableDefinition(
                name="name",
                display_name="Name",
                max_length=20,
                pattern="^[a-z]+$",
            )
        ]
        schema = TemplateManager.generate_json_schema(variables)
        prop = schema["properties"]["name"]
        assert prop["type"] == "string"
        assert prop["maxLength"] == 20
        assert prop["pattern"] == "^[a-z]+$"

    def test_schema_enum_variable(self):
        """Test JSON Schema for enum variable."""
        variables = [
            EnumVariableDefinition(
                name="version", display_name="Version", options=["1.20", "1.21"]
            )
        ]
        schema = TemplateManager.generate_json_schema(variables)
        prop = schema["properties"]["version"]
        assert prop["type"] == "string"
        assert prop["enum"] == ["1.20", "1.21"]

    def test_schema_bool_variable(self):
        """Test JSON Schema for boolean variable."""
        variables = [
            BoolVariableDefinition(name="enabled", display_name="Enabled", default=True)
        ]
        schema = TemplateManager.generate_json_schema(variables)
        prop = schema["properties"]["enabled"]
        assert prop["type"] == "boolean"
        assert prop["default"] is True


class TestValidateVariableValues:
    """Test variable value validation."""

    def test_validate_int_type_error(self):
        """Test validation fails for wrong int type."""
        variables = [IntVariableDefinition(name="port", display_name="Port")]
        errors = TemplateManager.validate_variable_values(variables, {"port": "25565"})
        assert any("必须是整数" in e for e in errors)

    def test_validate_int_bool_rejected(self):
        """Test that bool is rejected for int type."""
        variables = [IntVariableDefinition(name="port", display_name="Port")]
        errors = TemplateManager.validate_variable_values(variables, {"port": True})
        assert any("必须是整数" in e for e in errors)

    def test_validate_int_range_min(self):
        """Test validation fails for value below min."""
        variables = [
            IntVariableDefinition(name="port", display_name="Port", min_value=1024)
        ]
        errors = TemplateManager.validate_variable_values(variables, {"port": 80})
        assert any(">= 1024" in e for e in errors)

    def test_validate_int_range_max(self):
        """Test validation fails for value above max."""
        variables = [
            IntVariableDefinition(name="port", display_name="Port", max_value=65535)
        ]
        errors = TemplateManager.validate_variable_values(variables, {"port": 70000})
        assert any("<= 65535" in e for e in errors)

    def test_validate_float_type_error(self):
        """Test validation fails for wrong float type."""
        variables = [FloatVariableDefinition(name="ratio", display_name="Ratio")]
        errors = TemplateManager.validate_variable_values(variables, {"ratio": "0.5"})
        assert any("必须是数字" in e for e in errors)

    def test_validate_float_accepts_int(self):
        """Test that int is accepted for float type."""
        variables = [FloatVariableDefinition(name="ratio", display_name="Ratio")]
        errors = TemplateManager.validate_variable_values(variables, {"ratio": 1})
        assert errors == []

    def test_validate_string_type_error(self):
        """Test validation fails for wrong string type."""
        variables = [StringVariableDefinition(name="name", display_name="Name")]
        errors = TemplateManager.validate_variable_values(variables, {"name": 123})
        assert any("必须是字符串" in e for e in errors)

    def test_validate_string_max_length(self):
        """Test validation fails for string exceeding max length."""
        variables = [
            StringVariableDefinition(name="name", display_name="Name", max_length=5)
        ]
        errors = TemplateManager.validate_variable_values(
            variables, {"name": "toolong"}
        )
        assert any("超过最大长度" in e for e in errors)

    def test_validate_string_pattern(self):
        """Test validation fails for string not matching pattern."""
        variables = [
            StringVariableDefinition(
                name="name", display_name="Name", pattern="^[a-z]+$"
            )
        ]
        errors = TemplateManager.validate_variable_values(
            variables, {"name": "Invalid123"}
        )
        assert any("不匹配模式" in e for e in errors)

    def test_validate_enum_invalid_option(self):
        """Test validation fails for invalid enum option."""
        variables = [
            EnumVariableDefinition(
                name="version", display_name="Version", options=["1.20", "1.21"]
            )
        ]
        errors = TemplateManager.validate_variable_values(
            variables, {"version": "1.19"}
        )
        assert any("必须是以下之一" in e for e in errors)

    def test_validate_bool_type_error(self):
        """Test validation fails for wrong bool type."""
        variables = [BoolVariableDefinition(name="enabled", display_name="Enabled")]
        errors = TemplateManager.validate_variable_values(
            variables, {"enabled": "true"}
        )
        assert any("必须是布尔值" in e for e in errors)

    def test_validate_missing_required(self):
        """Test validation fails for missing required variable."""
        variables = [IntVariableDefinition(name="port", display_name="Port")]
        errors = TemplateManager.validate_variable_values(variables, {})
        assert any("缺少必需的变量" in e for e in errors)

    def test_validate_success(self):
        """Test validation passes for valid values."""
        variables = [
            IntVariableDefinition(
                name="port", display_name="Port", min_value=1024, max_value=65535
            ),
            StringVariableDefinition(
                name="name", display_name="Name", pattern="^[a-z-]+$"
            ),
            EnumVariableDefinition(
                name="version", display_name="Version", options=["1.20", "1.21"]
            ),
            BoolVariableDefinition(name="enabled", display_name="Enabled"),
        ]
        values = {
            "port": 25565,
            "name": "test-server",
            "version": "1.20",
            "enabled": True,
        }
        errors = TemplateManager.validate_variable_values(variables, values)
        assert errors == []


class TestGetDefaultValues:
    """Test default value extraction."""

    def test_get_defaults(self):
        """Test extracting default values from variables."""
        variables = [
            IntVariableDefinition(name="port", display_name="Port", default=25565),
            StringVariableDefinition(name="name", display_name="Name"),
            BoolVariableDefinition(name="enabled", display_name="Enabled", default=True),
        ]
        defaults = TemplateManager.get_default_values(variables)
        assert defaults == {"port": 25565, "enabled": True}

    def test_get_defaults_empty(self):
        """Test extracting defaults when none are set."""
        variables = [
            IntVariableDefinition(name="port", display_name="Port"),
            StringVariableDefinition(name="name", display_name="Name"),
        ]
        defaults = TemplateManager.get_default_values(variables)
        assert defaults == {}
