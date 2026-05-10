"""Template engine for variable parsing, validation, and replacement."""

import re
from collections.abc import Sequence
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
    """Variable parsing, validation, and ``{name}`` placeholder rendering for templates."""

    VARIABLE_PATTERN = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")

    @classmethod
    def extract_variables_from_yaml(cls, yaml_template: str) -> set[str]:
        return set(cls.VARIABLE_PATTERN.findall(yaml_template))

    @classmethod
    def validate_template(
        cls,
        yaml_template: str,
        user_variables: Sequence[VariableDefinition],
    ) -> list[str]:
        """Verify no duplicate names and that YAML/definition variable sets match exactly."""
        errors = []

        yaml_vars = cls.extract_variables_from_yaml(yaml_template)

        user_var_names = {v.name for v in user_variables}

        if len(user_var_names) != len(user_variables):
            seen = set()
            duplicates = set()
            for v in user_variables:
                if v.name in seen:
                    duplicates.add(v.name)
                seen.add(v.name)
            if duplicates:
                errors.append(f"用户变量名重复: {', '.join(sorted(duplicates))}")

        undefined = yaml_vars - user_var_names
        if undefined:
            errors.append(f"YAML 中使用了未定义的变量: {', '.join(sorted(undefined))}")

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
        """Replace ``{var}`` placeholders. Raises ``ValueError`` when a value is missing."""

        def replace_var(match: re.Match) -> str:
            var_name = match.group(1)
            if var_name in variable_values:
                return str(variable_values[var_name])
            raise ValueError(f"变量 '{var_name}' 未提供值")

        return cls.VARIABLE_PATTERN.sub(replace_var, yaml_template)

    @classmethod
    def generate_json_schema(
        cls,
        user_variables: Sequence[VariableDefinition],
    ) -> dict:
        """Generate the rjsf JSON Schema describing ``user_variables``."""
        properties = {}
        required = []

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
            schema = {**base, "type": "string"}

        return schema

    @classmethod
    def validate_variable_values(
        cls,
        user_variables: Sequence[VariableDefinition],
        values: dict[str, Any],
    ) -> list[str]:
        """Type/range/pattern check ``values`` against ``user_variables``."""
        errors = []

        for var in user_variables:
            if var.name not in values:
                errors.append(f"缺少必需的变量: {var.name}")
                continue

            value = values[var.name]

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
        user_variables: Sequence[VariableDefinition],
    ) -> dict[str, Any]:
        defaults = {}

        for var in user_variables:
            if var.default is not None:
                defaults[var.name] = var.default

        return defaults

    @classmethod
    def extract_variables_from_compose(
        cls,
        yaml_template: str,
        compose_yaml: str,
        variable_definitions: Sequence[VariableDefinition],
    ) -> tuple[dict[str, Any], list[str]]:
        """Recover variable values from a rendered compose by line-regex matching.

        For each template line containing ``{var}`` placeholders, build a
        regex with named capture groups and match against compose lines.
        Returns ``(extracted_values, warnings)``.
        """
        extracted: dict[str, Any] = {}
        warnings: list[str] = []

        var_def_map = {v.name: v for v in variable_definitions}

        template_vars = cls.extract_variables_from_yaml(yaml_template)

        template_lines = yaml_template.splitlines()
        compose_lines = compose_yaml.splitlines()

        for template_line in template_lines:
            line_vars = cls.VARIABLE_PATTERN.findall(template_line)
            if not line_vars:
                continue

            pattern = cls._template_line_to_regex(template_line, line_vars)
            if not pattern:
                continue

            for compose_line in compose_lines:
                match = re.match(pattern, compose_line)
                if match:
                    for var_name in line_vars:
                        if var_name in match.groupdict():
                            raw_value = match.group(var_name)
                            if var_name not in extracted:
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

        for var_name in template_vars:
            if var_name not in extracted:
                if (
                    var_name in var_def_map
                    and var_def_map[var_name].default is not None
                ):
                    extracted[var_name] = var_def_map[var_name].default
                    warnings.append(
                        f"变量 '{var_name}' 未能从 compose 文件中提取，使用默认值"
                    )
                else:
                    warnings.append(
                        f"变量 '{var_name}' 未能从 compose 文件中提取，且无默认值"
                    )

        return extracted, warnings

    @classmethod
    def _template_line_to_regex(cls, line: str, variables: list[str]) -> str | None:
        """Build a line regex with named groups for first uses and backrefs for repeats."""
        pattern = re.escape(line.strip())

        seen_vars: set[str] = set()

        for var in variables:
            escaped_placeholder = re.escape(f"{{{var}}}")
            if var not in seen_vars:
                pattern = pattern.replace(escaped_placeholder, f"(?P<{var}>.+?)", 1)
                seen_vars.add(var)
            else:
                pattern = pattern.replace(escaped_placeholder, f"(?P={var})")

        return f"^\\s*{pattern}\\s*$"

    @classmethod
    def _convert_to_typed_value(
        cls,
        raw: str,
        var_def: VariableDefinition,
    ) -> tuple[Any, str | None]:
        """Coerce ``raw`` to ``var_def``'s type. Returns ``(value, warning_or_None)``."""
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
            else:
                return raw, None
        except (ValueError, TypeError) as e:
            return raw, f"变量 '{var_def.name}' 类型转换失败: {e}"
