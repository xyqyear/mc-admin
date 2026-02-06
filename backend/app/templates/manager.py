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
        1. No duplicate variable names
        2. YAML variables and user variables match exactly (bidirectional)

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

        # Bidirectional matching: YAML vars must match user vars exactly
        # Variables in YAML but not defined
        undefined = yaml_vars - user_var_names
        if undefined:
            errors.append(f"YAML 中使用了未定义的变量: {', '.join(sorted(undefined))}")

        # Variables defined but not used in YAML
        unused = user_var_names - yaml_vars
        if unused:
            errors.append(
                f"已定义但未在 YAML 中使用的变量: {', '.join(sorted(unused))}"
            )

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

        Args:
            user_variables: List of user-defined variable definitions

        Returns:
            JSON Schema dictionary for rjsf form rendering
        """
        properties = {}
        required = []

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

        for var in user_variables:
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
        """Get default values for all variables.

        Args:
            user_variables: List of user-defined variable definitions

        Returns:
            Dictionary mapping variable names to their default values
        """
        defaults = {}

        # Add user variable defaults
        for var in user_variables:
            if var.default is not None:
                defaults[var.name] = var.default

        return defaults

    @classmethod
    def extract_variables_from_compose(
        cls,
        yaml_template: str,
        compose_yaml: str,
        variable_definitions: list[VariableDefinition],
    ) -> tuple[dict[str, Any], list[str]]:
        """Extract variable values from compose file by matching against template.

        Algorithm:
        1. For each line in template containing {variable} placeholders
        2. Convert that line to a regex pattern (escape special chars, replace {var} with capture group)
        3. Search all lines in compose file for matches
        4. Extract captured values and convert to appropriate types

        Args:
            yaml_template: YAML template string with {variable} placeholders
            compose_yaml: Actual compose YAML to extract values from
            variable_definitions: List of variable definitions for type conversion

        Returns:
            Tuple of (extracted_values dict, warnings list)
        """
        extracted: dict[str, Any] = {}
        warnings: list[str] = []

        # Build variable name to definition map
        var_def_map = {v.name: v for v in variable_definitions}

        # Get all variable names from template
        template_vars = cls.extract_variables_from_yaml(yaml_template)

        # Process each line in template that contains variables
        template_lines = yaml_template.splitlines()
        compose_lines = compose_yaml.splitlines()

        for template_line in template_lines:
            line_vars = cls.VARIABLE_PATTERN.findall(template_line)
            if not line_vars:
                continue

            # Build regex pattern for this line
            pattern = cls._template_line_to_regex(template_line, line_vars)
            if not pattern:
                continue

            # Search in compose lines
            for compose_line in compose_lines:
                match = re.match(pattern, compose_line)
                if match:
                    # Extract values from named groups
                    for var_name in line_vars:
                        if var_name in match.groupdict():
                            raw_value = match.group(var_name)
                            if var_name not in extracted:
                                # Convert to typed value
                                if var_name in var_def_map:
                                    typed_value, warning = cls._convert_to_typed_value(
                                        raw_value, var_def_map[var_name]
                                    )
                                    extracted[var_name] = typed_value
                                    if warning:
                                        warnings.append(warning)
                                else:
                                    extracted[var_name] = raw_value
                    break

        # Check for missing variables and use defaults
        for var_name in template_vars:
            if var_name not in extracted:
                if var_name in var_def_map and var_def_map[var_name].default is not None:
                    extracted[var_name] = var_def_map[var_name].default
                    warnings.append(f"变量 '{var_name}' 未能从 compose 文件中提取，使用默认值")
                else:
                    warnings.append(f"变量 '{var_name}' 未能从 compose 文件中提取，且无默认值")

        return extracted, warnings

    @classmethod
    def _template_line_to_regex(cls, line: str, variables: list[str]) -> str | None:
        """Convert a template line to a regex pattern with named capture groups.

        Args:
            line: Template line containing {variable} placeholders
            variables: List of variable names in this line

        Returns:
            Regex pattern string, or None if conversion fails
        """
        # Escape special regex characters in the line
        pattern = re.escape(line.strip())

        # Track which variables we've seen for backreferences
        seen_vars: set[str] = set()

        for var in variables:
            escaped_placeholder = re.escape(f"{{{var}}}")
            if var not in seen_vars:
                # First occurrence: use named capture group
                pattern = pattern.replace(escaped_placeholder, f"(?P<{var}>.+?)", 1)
                seen_vars.add(var)
            else:
                # Subsequent occurrences: use backreference
                pattern = pattern.replace(escaped_placeholder, f"(?P={var})")

        return f"^\\s*{pattern}\\s*$"

    @classmethod
    def _convert_to_typed_value(
        cls,
        raw: str,
        var_def: VariableDefinition,
    ) -> tuple[Any, str | None]:
        """Convert raw string value to typed value based on variable definition.

        Args:
            raw: Raw string value extracted from compose
            var_def: Variable definition for type information

        Returns:
            Tuple of (converted_value, warning_message or None)
        """
        try:
            if isinstance(var_def, IntVariableDefinition):
                return int(raw), None
            elif isinstance(var_def, FloatVariableDefinition):
                return float(raw), None
            elif isinstance(var_def, BoolVariableDefinition):
                return raw.lower() in ("true", "1", "yes"), None
            elif isinstance(var_def, EnumVariableDefinition):
                if raw in var_def.options:
                    return raw, None
                else:
                    return raw, f"变量 '{var_def.name}' 的值 '{raw}' 不在选项列表中"
            else:  # StringVariableDefinition
                return raw, None
        except (ValueError, TypeError) as e:
            return raw, f"变量 '{var_def.name}' 类型转换失败: {e}"
