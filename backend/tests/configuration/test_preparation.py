from dataclasses import FrozenInstanceError

import pytest

from app.configuration.preparation import prepare_template_configuration
from app.templates import StringVariableDefinition, TemplateSnapshot


def test_preparation_captures_deeply_immutable_source_and_defaults():
    snapshot = TemplateSnapshot(
        template_id=1, template_name="保留来源", snapshot_time="2026-09-25T00:00:00Z",
        yaml_template="memory: {memory}",
        variable_definitions=[StringVariableDefinition(name="memory", display_name="内存", default="2G")],
    )
    supplied = {"extra": {"values": [1, 2]}}
    prepared = prepare_template_configuration(snapshot, supplied)
    supplied["extra"]["values"].append(3)
    snapshot.yaml_template = "changed"
    variable = snapshot.variable_definitions[0]
    assert isinstance(variable, StringVariableDefinition)
    variable.default = "8G"
    assert prepared.variable_values == {"memory": "2G", "extra": {"values": [1, 2]}}
    values = prepared.variable_values
    assert values is not None
    values["extra"]["values"].clear()
    copied = prepared.template_snapshot
    assert copied is not None
    copied.variable_definitions.clear()
    assert prepared.yaml_content == "memory: 2G"
    assert prepared.variable_values == {"memory": "2G", "extra": {"values": [1, 2]}}
    assert prepared.template_snapshot is not None
    assert len(prepared.template_snapshot.variable_definitions) == 1
    with pytest.raises(FrozenInstanceError):
        prepared.__setattr__("yaml_content", "bad")
