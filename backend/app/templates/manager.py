"""Template engine for variable parsing, validation, and replacement."""

import re
from typing import Any

from .models import (
    BoolVariableDefinition,
    EnumVariableDefinition,
    FloatVariableDefinition,
    IntVariableDefinition,
    StringVariableDefinition,
    VariableDefinition,
    get_system_reserved_variables,
    get_system_variable_names,
)


class TemplateManager:
    """Template engine for variable parsing, validation, and replacement."""

    # Pattern to match {variable_name} placeholders
    VARIABLE_PATTERN = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")

    @classmethod
    def extract_variables_from_yaml(cls, yaml_template: str) -> set[str]:
        """Extract all {variable} placeholders from YAML template.

        Args:
            yaml_template: YAML template string with {variable} placeholders

        Returns:
            Set of variable names found in the template
        """
        return set(cls.VARIABLE_PATTERN.findall(yaml_template))

    @classmethod
    def validate_template(
        cls,
        yaml_template: str,
        user_variables: list[VariableDefinition],
    ) -> list[str]:
        """Validate template consistency.

        Checks that:
        1. User variables don't conflict with system reserved variables
        2. All variables used in YAML are defined (system or user)

        Args:
            yaml_template: YAML template string
            user_variables: List of user-defined variable definitions

        Returns:
            List of error messages. Empty list means valid.
        """
        errors = []

        # Extract variables from YAML
        yaml_vars = cls.extract_variables_from_yaml(yaml_template)

        # Build set of user variable names
        user_var_names = {v.name for v in user_variables}

        # Check for user variables that conflict with system variables
        system_var_names = get_system_variable_names()
        conflicts = user_var_names & system_var_names
        if conflicts:
            errors.append(f"用户变量与系统保留变量冲突: {', '.join(sorted(conflicts))}")

        # Check for duplicate user variable names
        if len(user_var_names) != len(user_variables):
            seen = set()
            duplicates = set()
            for v in user_variables:
                if v.name in seen:
                    duplicates.add(v.name)
                seen.add(v.name)
            if duplicates:
                errors.append(f"用户变量名重复: {', '.join(sorted(duplicates))}")

        # Build set of all defined variables (system + user)
        defined_vars = system_var_names | user_var_names

        # Check for undefined variables in YAML
        undefined = yaml_vars - defined_vars
        if undefined:
            errors.append(f"YAML 中使用了未定义的变量: {', '.join(sorted(undefined))}")

        return errors

    @classmethod
    def render_yaml(
        cls,
        yaml_template: str,
        variable_values: dict[str, Any],
    ) -> str:
        """Replace all {variable} placeholders with actual values.

        Args:
            yaml_template: YAML template string with placeholders
            variable_values: Dictionary mapping variable names to values

        Returns:
            Rendered YAML string with all placeholders replaced

        Raises:
            ValueError: If a variable in the template is not provided
        """

        def replace_var(match: re.Match) -> str:
            var_name = match.group(1)
            if var_name in variable_values:
                return str(variable_values[var_name])
            raise ValueError(f"变量 '{var_name}' 未提供值")

        return cls.VARIABLE_PATTERN.sub(replace_var, yaml_template)

    @classmethod
    def generate_json_schema(
        cls,
        user_variables: list[VariableDefinition],
    ) -> dict:
        """Generate JSON Schema for rjsf from template variables.

        System variables are always included with fixed schema.
        User variables are added dynamically.

        Args:
            user_variables: List of user-defined variable definitions

        Returns:
            JSON Schema dictionary for rjsf form rendering
        """
        properties = {}
        required = []

        # Add system variables first (fixed order)
        for var in get_system_reserved_variables():
            prop_schema = cls._variable_to_json_schema(var)
            properties[var.name] = prop_schema
            required.append(var.name)

        # Add user variables
        for var in user_variables:
            prop_schema = cls._variable_to_json_schema(var)
            properties[var.name] = prop_schema
            required.append(var.name)

        return {"type": "object", "properties": properties, "required": required}

    @classmethod
    def _variable_to_json_schema(
        cls,
        var: IntVariableDefinition
        | FloatVariableDefinition
        | StringVariableDefinition
        | EnumVariableDefinition
        | BoolVariableDefinition,
    ) -> dict:
        """Convert a variable definition to JSON Schema property.

        Args:
            var: Variable definition

        Returns:
            JSON Schema property dictionary
        """
        base: dict[str, Any] = {
            "title": var.display_name,
            "description": var.description or "",
        }
        if var.default is not None:
            base["default"] = var.default

        if isinstance(var, IntVariableDefinition):
            schema = {**base, "type": "integer"}
            if var.min_value is not None:
                schema["minimum"] = var.min_value
            if var.max_value is not None:
                schema["maximum"] = var.max_value

        elif isinstance(var, FloatVariableDefinition):
            schema = {**base, "type": "number"}
            if var.min_value is not None:
                schema["minimum"] = var.min_value
            if var.max_value is not None:
                schema["maximum"] = var.max_value

        elif isinstance(var, StringVariableDefinition):
            schema = {**base, "type": "string"}
            if var.max_length is not None:
                schema["maxLength"] = var.max_length
            if var.pattern is not None:
                schema["pattern"] = var.pattern

        elif isinstance(var, EnumVariableDefinition):
            schema = {**base, "type": "string", "enum": var.options}

        elif isinstance(var, BoolVariableDefinition):
            schema = {**base, "type": "boolean"}

        else:
            # Fallback for unknown types
            schema = {**base, "type": "string"}

        return schema

    @classmethod
    def validate_variable_values(
        cls,
        user_variables: list[VariableDefinition],
        values: dict[str, Any],
    ) -> list[str]:
        """Validate variable values against their definitions.

        Args:
            user_variables: List of user-defined variable definitions
            values: Dictionary of variable values to validate

        Returns:
            List of error messages. Empty list means valid.
        """
        errors = []
        all_vars: list[
            IntVariableDefinition
            | FloatVariableDefinition
            | StringVariableDefinition
            | EnumVariableDefinition
            | BoolVariableDefinition
        ] = list(get_system_reserved_variables()) + list(user_variables)

        for var in all_vars:
            if var.name not in values:
                errors.append(f"缺少必需的变量: {var.name}")
                continue

            value = values[var.name]

            # Type validation
            if isinstance(var, IntVariableDefinition):
                if not isinstance(value, int) or isinstance(value, bool):
                    errors.append(f"变量 '{var.name}' 必须是整数")
                elif var.min_value is not None and value < var.min_value:
                    errors.append(f"变量 '{var.name}' 必须 >= {var.min_value}")
                elif var.max_value is not None and value > var.max_value:
                    errors.append(f"变量 '{var.name}' 必须 <= {var.max_value}")

            elif isinstance(var, FloatVariableDefinition):
                if not isinstance(value, (int, float)) or isinstance(value, bool):
                    errors.append(f"变量 '{var.name}' 必须是数字")
                elif var.min_value is not None and value < var.min_value:
                    errors.append(f"变量 '{var.name}' 必须 >= {var.min_value}")
                elif var.max_value is not None and value > var.max_value:
                    errors.append(f"变量 '{var.name}' 必须 <= {var.max_value}")

            elif isinstance(var, StringVariableDefinition):
                if not isinstance(value, str):
                    errors.append(f"变量 '{var.name}' 必须是字符串")
                elif var.max_length is not None and len(value) > var.max_length:
                    errors.append(f"变量 '{var.name}' 超过最大长度 {var.max_length}")
                elif var.pattern is not None and not re.match(var.pattern, value):
                    errors.append(f"变量 '{var.name}' 不匹配模式 {var.pattern}")

            elif isinstance(var, EnumVariableDefinition):
                if value not in var.options:
                    errors.append(f"变量 '{var.name}' 必须是以下之一: {var.options}")

            elif isinstance(var, BoolVariableDefinition):
                if not isinstance(value, bool):
                    errors.append(f"变量 '{var.name}' 必须是布尔值")

        return errors

    @classmethod
    def get_default_values(
        cls,
        user_variables: list[VariableDefinition],
    ) -> dict[str, Any]:
        """Get default values for all variables (system + user).

        Args:
            user_variables: List of user-defined variable definitions

        Returns:
            Dictionary mapping variable names to their default values
        """
        defaults = {}

        # Add system variable defaults
        for var in get_system_reserved_variables():
            defaults[var.name] = var.default

        # Add user variable defaults
        for var in user_variables:
            if var.default is not None:
                defaults[var.name] = var.default

        return defaults
