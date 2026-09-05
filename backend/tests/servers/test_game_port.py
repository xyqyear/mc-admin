import pytest
import yaml

from app.minecraft.game_port import (
    get_game_port_mapping,
    validate_game_port_initialization,
)
from app.templates import IntVariableDefinition
from app.templates.manager import TemplateManager


def compose(environment=None, ports=None):
    return yaml.safe_dump({"services": {"mc": {
        "environment": environment if environment is not None else {"SERVER_PORT": 25565},
        "ports": ports if ports is not None else ["25517:25565"],
    }}})


@pytest.mark.parametrize("environment", [
    {"SERVER_PORT": 25565}, {"SERVER_PORT": "25565"}, ["SERVER_PORT=25565"],
    {"SERVER_PORT": 25565, "OVERRIDE_SERVER_PROPERTIES": "TRUE", "SKIP_SERVER_PROPERTIES": False},
])
@pytest.mark.parametrize("ports", [
    ["25517:25565"], ["127.0.0.1:25517:25565/tcp"],
    [{"target": 25565, "published": 25517}],
    [{"target": "25565", "published": "25517", "protocol": "tcp"}],
    ["25517:25565/udp", "25518:25565/tcp"],
])
def test_initialization_accepts_supported_forms(environment, ports):
    validate_game_port_initialization(compose(environment, ports))


@pytest.mark.parametrize("value", [None, "", True, False, 25517, 25565.5, "${GAME_PORT}", "{game_port}"])
def test_initialization_rejects_invalid_environment_port(value):
    with pytest.raises(ValueError, match="SERVER_PORT=25565"):
        validate_game_port_initialization(compose({"SERVER_PORT": value}))


@pytest.mark.parametrize("environment", [{}, [], ["SERVER_PORT"]])
def test_initialization_requires_explicit_port(environment):
    with pytest.raises(ValueError, match="SERVER_PORT"):
        validate_game_port_initialization(compose(environment))


@pytest.mark.parametrize("ports", [
    [], ["25517:25566"], ["25517:25565/udp"],
    [{"target": True}], [{"target": 25565.5}], [{"target": "${PORT}"}],
])
def test_initialization_requires_supported_tcp_target(ports):
    with pytest.raises(ValueError, match="TCP"):
        validate_game_port_initialization(compose(ports=ports))


@pytest.mark.parametrize("name,value", [
    ("OVERRIDE_SERVER_PROPERTIES", False), ("OVERRIDE_SERVER_PROPERTIES", "FALSE"),
    ("SKIP_SERVER_PROPERTIES", True), ("SKIP_SERVER_PROPERTIES", "TRUE"),
    ("SKIP_SERVER_PROPERTIES", None), ("SKIP_SERVER_PROPERTIES", "${SKIP}"),
    ("SKIP_SERVER_PROPERTIES", 0),
])
def test_initialization_rejects_disabled_or_unknown_property_management(name, value):
    with pytest.raises(ValueError, match=name):
        validate_game_port_initialization(compose({"SERVER_PORT": 25565, name: value}))


def test_mapping_read_ignores_environment_and_returns_container_target():
    for environment in ({}, {"SERVER_PORT": 25566, "SKIP_SERVER_PROPERTIES": True}):
        mapping = get_game_port_mapping(compose(environment))
        assert mapping.target == 25565
        assert mapping.published == "25517"


def test_template_host_placeholder_does_not_require_a_default():
    template = compose(ports=["{game_port}:25565"])
    variables = [IntVariableDefinition(name="game_port", display_name="Game port")]
    assert TemplateManager.validate_template(template, variables) == []


@pytest.mark.parametrize("template", [
    compose({"SERVER_PORT": "{port}"}),
    compose(ports=["25517:{port}"]),
    compose({"SERVER_PORT": 25565, "SKIP_SERVER_PROPERTIES": "{skip}"}),
])
def test_template_critical_values_must_be_literal(template):
    with pytest.raises(ValueError):
        validate_game_port_initialization(template, template=True)


def test_yaml_error_does_not_echo_configuration():
    with pytest.raises(ValueError) as error:
        get_game_port_mapping("services: [secret-value: [")
    assert "secret-value" not in str(error.value)
