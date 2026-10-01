"""Unit tests for variable extraction from compose files."""

import pytest

from app.templates import (
    BoolVariableDefinition,
    EnumVariableDefinition,
    FloatVariableDefinition,
    IntVariableDefinition,
    StringVariableDefinition,
)
from app.templates.manager import TemplateManager


class TestExtractVariablesFromCompose:
    """Tests for extract_variables_from_compose() function."""

    # --- Single variable extraction ---

    def test_extract_string_variable(self):
        """Extract a single string variable."""
        template = "container_name: mc-{name}"
        compose = "container_name: mc-survival"
        variables = [StringVariableDefinition(name="name", display_name="Name")]

        extracted, warnings = TemplateManager.extract_variables_from_compose(
            template, compose, variables
        )
        assert extracted["name"] == "survival"
        assert warnings == []

    def test_extract_int_variable(self):
        """Extract an integer variable with type conversion."""
        template = "port: {game_port}"
        compose = "port: 25565"
        variables = [IntVariableDefinition(name="game_port", display_name="Game Port")]

        extracted, warnings = TemplateManager.extract_variables_from_compose(
            template, compose, variables
        )
        assert extracted["game_port"] == 25565
        assert isinstance(extracted["game_port"], int)
        assert warnings == []

    def test_extract_float_variable(self):
        """Extract a float variable with type conversion."""
        template = "ratio: {ratio}"
        compose = "ratio: 0.75"
        variables = [FloatVariableDefinition(name="ratio", display_name="Ratio")]

        extracted, warnings = TemplateManager.extract_variables_from_compose(
            template, compose, variables
        )
        assert extracted["ratio"] == 0.75
        assert isinstance(extracted["ratio"], float)
        assert warnings == []

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [(value, True) for value in ("true", "True", "TRUE", "1", "yes", "Yes")]
        + [(value, False) for value in ("false", "False", "0", "no")],
    )
    def test_extract_bool_variable(self, raw, expected):
        template = "enabled: {flag}"
        compose = f"enabled: {raw}"
        variables = [BoolVariableDefinition(name="flag", display_name="Flag")]

        extracted, warnings = TemplateManager.extract_variables_from_compose(
            template, compose, variables
        )
        assert extracted["flag"] is expected
        assert warnings == []

    def test_extract_enum_variable_valid(self):
        """Extract a valid enum variable."""
        template = "version: {game_version}"
        compose = "version: 1.20.4"
        variables = [
            EnumVariableDefinition(
                name="game_version",
                display_name="Version",
                options=["1.20.4", "1.21.0"],
            )
        ]

        extracted, warnings = TemplateManager.extract_variables_from_compose(
            template, compose, variables
        )
        assert extracted["game_version"] == "1.20.4"
        assert warnings == []

    def test_extract_enum_variable_invalid_option(self):
        """Extract enum variable with value not in options produces warning."""
        template = "version: {game_version}"
        compose = "version: 1.19.0"
        variables = [
            EnumVariableDefinition(
                name="game_version",
                display_name="Version",
                options=["1.20.4", "1.21.0"],
            )
        ]

        extracted, warnings = TemplateManager.extract_variables_from_compose(
            template, compose, variables
        )
        assert extracted["game_version"] == "1.19.0"
        assert len(warnings) == 1
        assert "不在选项列表中" in warnings[0]

    # --- Multiple variables per line ---

    def test_two_variables_per_line_port_mapping(self):
        """Extract two variables from a port mapping line."""
        template = '- "{game_port}:{rcon_port}"'
        compose = '- "25565:25575"'
        variables = [
            IntVariableDefinition(name="game_port", display_name="Game Port"),
            IntVariableDefinition(name="rcon_port", display_name="RCON Port"),
        ]

        extracted, warnings = TemplateManager.extract_variables_from_compose(
            template, compose, variables
        )
        assert extracted["game_port"] == 25565
        assert extracted["rcon_port"] == 25575
        assert warnings == []

    def test_three_variables_per_line(self):
        """Extract three variables from a single line."""
        template = "url: http://{host}:{port}/{path}"
        compose = "url: http://localhost:8080/api"
        variables = [
            StringVariableDefinition(name="host", display_name="Host"),
            IntVariableDefinition(name="port", display_name="Port"),
            StringVariableDefinition(name="path", display_name="Path"),
        ]

        extracted, warnings = TemplateManager.extract_variables_from_compose(
            template, compose, variables
        )
        assert extracted["host"] == "localhost"
        assert extracted["port"] == 8080
        assert extracted["path"] == "api"
        assert warnings == []

    def test_image_format_three_variables(self):
        """Extract registry/image:tag format."""
        template = "image: {registry}/{image}:{tag}"
        compose = "image: docker.io/itzg/minecraft-server:latest"
        variables = [
            StringVariableDefinition(name="registry", display_name="Registry"),
            StringVariableDefinition(name="image", display_name="Image"),
            StringVariableDefinition(name="tag", display_name="Tag"),
        ]

        extracted, warnings = TemplateManager.extract_variables_from_compose(
            template, compose, variables
        )
        assert extracted["registry"] == "docker.io"
        assert extracted["image"] == "itzg/minecraft-server"
        assert extracted["tag"] == "latest"
        assert warnings == []

    def test_external_port_mapping(self):
        """Extract external port from port mapping with fixed internal port."""
        template = '- "{external_port}:25565"'
        compose = '- "30000:25565"'
        variables = [
            IntVariableDefinition(name="external_port", display_name="External Port"),
        ]

        extracted, warnings = TemplateManager.extract_variables_from_compose(
            template, compose, variables
        )
        assert extracted["external_port"] == 30000
        assert warnings == []

    # --- Backreference handling ---

    def test_backreference_same_variable_twice(self):
        """Same variable appearing twice on one line uses backreference."""
        template = "path: /{name}/{name}/data"
        compose = "path: /survival/survival/data"
        variables = [StringVariableDefinition(name="name", display_name="Name")]

        extracted, warnings = TemplateManager.extract_variables_from_compose(
            template, compose, variables
        )
        assert extracted["name"] == "survival"
        assert warnings == []

    def test_backreference_mismatch(self):
        """Backreference doesn't match if values differ — line won't match."""
        template = "path: /{name}/{name}/data"
        compose = "path: /foo/bar/data"
        variables = [StringVariableDefinition(name="name", display_name="Name")]

        extracted, warnings = TemplateManager.extract_variables_from_compose(
            template, compose, variables
        )
        # The regex backreference requires both to be the same, so no match
        assert "name" not in extracted or len(warnings) > 0

    def test_same_variable_on_different_lines(self):
        """Same variable on different lines — first match wins."""
        template = "first: {name}\nsecond: {name}"
        compose = "first: alpha\nsecond: beta"
        variables = [StringVariableDefinition(name="name", display_name="Name")]

        extracted, _ = TemplateManager.extract_variables_from_compose(
            template, compose, variables
        )
        # First match wins
        assert extracted["name"] == "alpha"

    # --- Type conversion failures ---

    def test_int_conversion_failure(self):
        """Non-numeric value for int variable produces warning."""
        template = "port: {port}"
        compose = "port: not_a_number"
        variables = [IntVariableDefinition(name="port", display_name="Port")]

        extracted, warnings = TemplateManager.extract_variables_from_compose(
            template, compose, variables
        )
        assert extracted["port"] == "not_a_number"  # Raw value kept
        assert len(warnings) == 1
        assert "类型转换失败" in warnings[0]

    def test_float_conversion_failure(self):
        """Non-numeric value for float variable produces warning."""
        template = "ratio: {ratio}"
        compose = "ratio: not_a_float"
        variables = [FloatVariableDefinition(name="ratio", display_name="Ratio")]

        extracted, warnings = TemplateManager.extract_variables_from_compose(
            template, compose, variables
        )
        assert extracted["ratio"] == "not_a_float"
        assert len(warnings) == 1
        assert "类型转换失败" in warnings[0]

    # --- Default values ---

    def test_missing_variable_with_default(self):
        """Missing variable falls back to default value with warning."""
        template = "name: {name}\nport: {port}"
        compose = "name: survival"
        variables = [
            StringVariableDefinition(name="name", display_name="Name"),
            IntVariableDefinition(name="port", display_name="Port", default=25565),
        ]

        extracted, warnings = TemplateManager.extract_variables_from_compose(
            template, compose, variables
        )
        assert extracted["name"] == "survival"
        assert extracted["port"] == 25565
        assert any("使用默认值" in w for w in warnings)

    def test_missing_variable_without_default(self):
        """Missing variable without default produces warning."""
        template = "name: {name}\nport: {port}"
        compose = "name: survival"
        variables = [
            StringVariableDefinition(name="name", display_name="Name"),
            IntVariableDefinition(name="port", display_name="Port"),
        ]

        extracted, warnings = TemplateManager.extract_variables_from_compose(
            template, compose, variables
        )
        assert extracted["name"] == "survival"
        assert "port" not in extracted
        assert any("无默认值" in w for w in warnings)

    def test_all_variables_missing(self):
        """No matches at all — defaults used where available."""
        template = "name: {name}\nport: {port}"
        compose = "something: else"
        variables = [
            StringVariableDefinition(name="name", display_name="Name", default="default"),
            IntVariableDefinition(name="port", display_name="Port"),
        ]

        extracted, warnings = TemplateManager.extract_variables_from_compose(
            template, compose, variables
        )
        assert extracted["name"] == "default"
        assert "port" not in extracted
        assert len(warnings) == 2

    # --- Real-world scenarios ---

    def test_full_minecraft_compose(self):
        """Extract variables from a realistic Minecraft Docker Compose template."""
        template = """\
version: '3.8'
services:
  mc:
    image: itzg/minecraft-server:latest
    container_name: mc-{name}
    ports:
      - "{game_port}:25565"
      - "{rcon_port}:25575"
    environment:
      EULA: "TRUE"
      VERSION: "{game_version}"
      TYPE: "{server_type}"
"""
        compose = """\
version: '3.8'
services:
  mc:
    image: itzg/minecraft-server:latest
    container_name: mc-survival
    ports:
      - "30000:25565"
      - "30001:25575"
    environment:
      EULA: "TRUE"
      VERSION: "1.20.4"
      TYPE: "PAPER"
"""
        variables = [
            StringVariableDefinition(name="name", display_name="Name"),
            IntVariableDefinition(name="game_port", display_name="Game Port"),
            IntVariableDefinition(name="rcon_port", display_name="RCON Port"),
            StringVariableDefinition(name="game_version", display_name="Version"),
            EnumVariableDefinition(
                name="server_type",
                display_name="Server Type",
                options=["VANILLA", "PAPER", "FORGE"],
            ),
        ]

        extracted, warnings = TemplateManager.extract_variables_from_compose(
            template, compose, variables
        )
        assert extracted["name"] == "survival"
        assert extracted["game_port"] == 30000
        assert extracted["rcon_port"] == 30001
        assert extracted["game_version"] == "1.20.4"
        assert extracted["server_type"] == "PAPER"
        assert warnings == []

    def test_special_regex_characters_in_template(self):
        """Template with regex special chars (dots, brackets) is handled."""
        template = "path: /opt/mc[server].data/{name}"
        compose = "path: /opt/mc[server].data/survival"
        variables = [StringVariableDefinition(name="name", display_name="Name")]

        extracted, warnings = TemplateManager.extract_variables_from_compose(
            template, compose, variables
        )
        assert extracted["name"] == "survival"
        assert warnings == []

    def test_indented_template_lines(self):
        """Template lines with leading whitespace are matched correctly."""
        template = "services:\n  mc:\n    container_name: mc-{name}"
        compose = "services:\n  mc:\n    container_name: mc-creative"
        variables = [StringVariableDefinition(name="name", display_name="Name")]

        extracted, warnings = TemplateManager.extract_variables_from_compose(
            template, compose, variables
        )
        assert extracted["name"] == "creative"
        assert warnings == []

    def test_no_variables_in_template(self):
        """Template with no variables returns empty dict."""
        template = "version: '3.8'"
        compose = "version: '3.8'"
        variables = []

        extracted, warnings = TemplateManager.extract_variables_from_compose(
            template, compose, variables
        )
        assert extracted == {}
        assert warnings == []

    def test_variable_without_definition(self):
        """Variable in template without definition is extracted as raw string."""
        template = "name: {name}\nport: {port}"
        compose = "name: survival\nport: 25565"
        # Only define 'name', not 'port'
        variables = [StringVariableDefinition(name="name", display_name="Name")]

        extracted, _warnings = TemplateManager.extract_variables_from_compose(
            template, compose, variables
        )
        assert extracted["name"] == "survival"
        assert extracted["port"] == "25565"  # Raw string, no type conversion

    def test_quoted_vs_unquoted_values(self):
        """Values inside quotes are extracted without the quotes."""
        template = 'VERSION: "{version}"'
        compose = 'VERSION: "1.20.4"'
        variables = [StringVariableDefinition(name="version", display_name="Version")]

        extracted, warnings = TemplateManager.extract_variables_from_compose(
            template, compose, variables
        )
        assert extracted["version"] == "1.20.4"
        assert warnings == []
