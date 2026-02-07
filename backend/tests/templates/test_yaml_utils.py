"""Unit tests for YAML comparison utility."""

from app.templates.yaml_utils import are_yaml_semantically_equal


class TestYamlSemanticEquality:
    """Tests for are_yaml_semantically_equal() function."""

    # --- Basic equality ---

    def test_identical_yaml(self):
        """Identical YAML strings are equal."""
        yaml = "name: test\nport: 25565"
        assert are_yaml_semantically_equal(yaml, yaml) is True

    def test_different_dict_key_order(self):
        """Dict key ordering differences are ignored."""
        yaml1 = "name: test\nport: 25565"
        yaml2 = "port: 25565\nname: test"
        assert are_yaml_semantically_equal(yaml1, yaml2) is True

    def test_different_list_order(self):
        """List element ordering matters."""
        yaml1 = "ports:\n  - 8080\n  - 8081"
        yaml2 = "ports:\n  - 8081\n  - 8080"
        assert are_yaml_semantically_equal(yaml1, yaml2) is False

    def test_different_values(self):
        """Different values are not equal."""
        yaml1 = "name: test"
        yaml2 = "name: other"
        assert are_yaml_semantically_equal(yaml1, yaml2) is False

    # --- Complex structures ---

    def test_nested_dicts(self):
        """Nested dict key order is ignored."""
        yaml1 = "services:\n  mc:\n    image: test\n    port: 25565"
        yaml2 = "services:\n  mc:\n    port: 25565\n    image: test"
        assert are_yaml_semantically_equal(yaml1, yaml2) is True

    def test_nested_dicts_different_values(self):
        """Nested dicts with different values are not equal."""
        yaml1 = "services:\n  mc:\n    image: test"
        yaml2 = "services:\n  mc:\n    image: other"
        assert are_yaml_semantically_equal(yaml1, yaml2) is False

    def test_lists_of_dicts(self):
        """Lists of dicts preserve order."""
        yaml1 = "items:\n  - name: a\n  - name: b"
        yaml2 = "items:\n  - name: b\n  - name: a"
        assert are_yaml_semantically_equal(yaml1, yaml2) is False

    def test_docker_compose_structure(self):
        """Docker Compose-like structure with reordered keys."""
        yaml1 = """\
version: '3.8'
services:
  mc:
    image: itzg/minecraft-server
    ports:
      - "25565:25565"
    environment:
      EULA: "TRUE"
"""
        yaml2 = """\
services:
  mc:
    environment:
      EULA: "TRUE"
    image: itzg/minecraft-server
    ports:
      - "25565:25565"
version: '3.8'
"""
        assert are_yaml_semantically_equal(yaml1, yaml2) is True

    # --- Edge cases ---

    def test_empty_yaml(self):
        """Two empty YAML strings are equal (both parse to None)."""
        assert are_yaml_semantically_equal("", "") is True

    def test_empty_vs_nonempty(self):
        """Empty vs non-empty YAML are not equal."""
        assert are_yaml_semantically_equal("", "name: test") is False

    def test_whitespace_differences(self):
        """Extra whitespace is ignored by YAML parser."""
        yaml1 = "name:   test"
        yaml2 = "name: test"
        assert are_yaml_semantically_equal(yaml1, yaml2) is True

    def test_trailing_newlines(self):
        """Trailing newlines don't affect equality."""
        yaml1 = "name: test\n"
        yaml2 = "name: test\n\n\n"
        assert are_yaml_semantically_equal(yaml1, yaml2) is True

    def test_comments_ignored(self):
        """YAML comments are stripped during parsing."""
        yaml1 = "# comment\nname: test"
        yaml2 = "name: test"
        assert are_yaml_semantically_equal(yaml1, yaml2) is True

    def test_numeric_types(self):
        """Numeric values are parsed to the same types."""
        yaml1 = "port: 25565"
        yaml2 = "port: 25565"
        assert are_yaml_semantically_equal(yaml1, yaml2) is True

    def test_numeric_string_vs_int(self):
        """Quoted number (string) vs unquoted number (int) are different."""
        yaml1 = 'port: "25565"'
        yaml2 = "port: 25565"
        assert are_yaml_semantically_equal(yaml1, yaml2) is False

    def test_boolean_representations(self):
        """Different boolean representations parse to the same value."""
        yaml1 = "enabled: true"
        yaml2 = "enabled: True"
        assert are_yaml_semantically_equal(yaml1, yaml2) is True

    def test_multiline_strings(self):
        """Multiline strings with different styles but same content."""
        yaml1 = "desc: |\n  line1\n  line2\n"
        yaml2 = "desc: \"line1\\nline2\\n\""
        assert are_yaml_semantically_equal(yaml1, yaml2) is True

    def test_flow_vs_block_style(self):
        """Flow and block style lists are equivalent."""
        yaml1 = "ports: [8080, 8081]"
        yaml2 = "ports:\n  - 8080\n  - 8081"
        assert are_yaml_semantically_equal(yaml1, yaml2) is True

    # --- Error handling ---

    def test_invalid_yaml_first(self):
        """Invalid first YAML returns False."""
        assert are_yaml_semantically_equal("{{invalid", "name: test") is False

    def test_invalid_yaml_second(self):
        """Invalid second YAML returns False."""
        assert are_yaml_semantically_equal("name: test", "{{invalid") is False

    def test_both_invalid_yaml(self):
        """Both invalid YAMLs return False."""
        assert are_yaml_semantically_equal("{{invalid", "}}invalid") is False

    def test_none_values_in_yaml(self):
        """YAML null values are equal."""
        yaml1 = "value: null"
        yaml2 = "value: ~"
        assert are_yaml_semantically_equal(yaml1, yaml2) is True
