"""Prepare server configuration and persist its matching template source."""

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Server, ServerTemplate
from ..templates import TemplateSnapshot, deserialize_variable_definitions_json
from ..templates.manager import TemplateManager
from .crud import get_active_server_by_id


@dataclass(frozen=True)
class ServerConfiguration:
    yaml_content: str
    template_snapshot: TemplateSnapshot | None = None
    variable_values: dict[str, Any] | None = None


def capture_template_snapshot(template: ServerTemplate) -> TemplateSnapshot:
    return TemplateSnapshot(
        template_id=template.id,
        template_name=template.name,
        yaml_template=template.yaml_template,
        variable_definitions=deserialize_variable_definitions_json(
            template.variable_definitions_json
        ),
        snapshot_time=datetime.now(UTC).isoformat(),
        source_updated_at=template.updated_at,
    )


def prepare_template_configuration(
    snapshot: TemplateSnapshot, variable_values: dict[str, Any]
) -> ServerConfiguration:
    errors = TemplateManager.validate_variable_values(
        snapshot.variable_definitions, variable_values
    )
    if errors:
        raise ValueError("; ".join(errors))
    return ServerConfiguration(
        yaml_content=TemplateManager.render_yaml(snapshot.yaml_template, variable_values),
        template_snapshot=snapshot.model_copy(deep=True),
        variable_values=variable_values.copy(),
    )


def prepare_snapshot_configuration(
    server: Server, variable_values: dict[str, Any]
) -> ServerConfiguration:
    if not server.template_id or not server.template_snapshot_json:
        raise ValueError("该服务器不是使用模板创建的")
    return prepare_template_configuration(
        TemplateSnapshot.model_validate_json(server.template_snapshot_json),
        variable_values,
    )


async def save_configuration_metadata(
    db: AsyncSession, server_id: str, configuration: ServerConfiguration
) -> None:
    snapshot = configuration.template_snapshot
    if snapshot is None:
        return
    server = await get_active_server_by_id(db, server_id)
    if server is None:
        raise ValueError("服务器不存在，无法保存配置来源")
    server.template_id = snapshot.template_id
    server.template_snapshot_json = snapshot.model_dump_json()
    server.variable_values_json = json.dumps(configuration.variable_values)
    server.updated_at = datetime.now(UTC)
    await db.commit()


async def clear_template_configuration(db: AsyncSession, server: Server) -> None:
    server.template_id = None
    server.template_snapshot_json = None
    server.variable_values_json = None
    server.updated_at = datetime.now(UTC)
    await db.commit()
