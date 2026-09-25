import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import yaml

from app.servers.models import Server
from app.templates.tables import ServerTemplate

from ..minecraft.compose import MCComposeFile
from ..minecraft.docker.compose_file import ComposeFile
from ..templates import TemplateSnapshot, deserialize_variable_definitions_json
from ..templates.manager import TemplateManager


def validate_server_configuration(server_id: str, yaml_content: str) -> tuple[int, int]:
    compose = MCComposeFile(ComposeFile.from_dict(yaml.safe_load(yaml_content)))
    if compose.get_server_name() != server_id:
        raise ValueError("服务器名称与 container_name 不匹配")
    return compose.get_game_port(), compose.get_rcon_port()


@dataclass(frozen=True, init=False)
class ServerConfiguration:
    yaml_content: str
    snapshot_json: str | None
    values_json: str | None
    expected_version: str | None

    def __init__(
        self, yaml_content: str, template_snapshot: TemplateSnapshot | None = None,
        variable_values: dict[str, Any] | None = None, *, expected_version: str | None = None,
    ) -> None:
        object.__setattr__(self, "yaml_content", yaml_content)
        object.__setattr__(self, "snapshot_json", template_snapshot.model_dump_json() if template_snapshot else None)
        object.__setattr__(self, "values_json", json.dumps(variable_values, sort_keys=True) if variable_values is not None else None)
        object.__setattr__(self, "expected_version", expected_version)

    @property
    def template_snapshot(self) -> TemplateSnapshot | None:
        return TemplateSnapshot.model_validate_json(self.snapshot_json) if self.snapshot_json else None

    @property
    def variable_values(self) -> dict[str, Any] | None:
        return json.loads(self.values_json) if self.values_json is not None else None

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(self.yaml_content.encode()).hexdigest()


def capture_template_snapshot(template: ServerTemplate) -> TemplateSnapshot:
    return TemplateSnapshot(
        template_id=template.id, template_name=template.name,
        yaml_template=template.yaml_template,
        variable_definitions=deserialize_variable_definitions_json(template.variable_definitions_json),
        snapshot_time=datetime.now(UTC).isoformat(), source_updated_at=template.updated_at,
    )


def prepare_template_configuration(
    snapshot: TemplateSnapshot, variable_values: dict[str, Any], *, expected_version: str | None = None,
) -> ServerConfiguration:
    values = TemplateManager.get_default_values(snapshot.variable_definitions) | variable_values
    errors = TemplateManager.validate_variable_values(snapshot.variable_definitions, values)
    if errors:
        raise ValueError("; ".join(errors))
    return ServerConfiguration(
        TemplateManager.render_yaml(snapshot.yaml_template, values), snapshot, values,
        expected_version=expected_version,
    )


def prepare_snapshot_configuration(
    server: Server, variable_values: dict[str, Any], *, expected_version: str | None = None,
) -> ServerConfiguration:
    if not server.template_id or not server.template_snapshot_json:
        raise ValueError("该服务器不是使用模板创建的")
    return prepare_template_configuration(
        TemplateSnapshot.model_validate_json(server.template_snapshot_json), variable_values,
        expected_version=expected_version,
    )
