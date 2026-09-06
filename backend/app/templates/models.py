"""Pydantic models for template variable definitions."""

from datetime import datetime
from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, Field, TypeAdapter, model_validator


class VariableType(str, Enum):
    INT = "int"
    FLOAT = "float"
    STRING = "string"
    ENUM = "enum"
    BOOL = "bool"


class IntVariableDefinition(BaseModel):
    type: Literal["int"] = "int"
    name: str = Field(min_length=1, max_length=50)
    display_name: str = Field(min_length=1, max_length=100)
    description: str | None = None
    default: int | None = None
    min_value: int | None = None
    max_value: int | None = None


class FloatVariableDefinition(BaseModel):
    type: Literal["float"] = "float"
    name: str = Field(min_length=1, max_length=50)
    display_name: str = Field(min_length=1, max_length=100)
    description: str | None = None
    default: float | None = None
    min_value: float | None = None
    max_value: float | None = None


class StringVariableDefinition(BaseModel):
    type: Literal["string"] = "string"
    name: str = Field(min_length=1, max_length=50)
    display_name: str = Field(min_length=1, max_length=100)
    description: str | None = None
    default: str | None = None
    max_length: int | None = None
    pattern: str | None = None


class EnumVariableDefinition(BaseModel):
    type: Literal["enum"] = "enum"
    name: str = Field(min_length=1, max_length=50)
    display_name: str = Field(min_length=1, max_length=100)
    description: str | None = None
    default: str | None = None
    options: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_default_in_options(self) -> "EnumVariableDefinition":
        if self.default is not None and self.default not in self.options:
            raise ValueError(
                f"默认值 '{self.default}' 必须是选项列表中的一个: {self.options}"
            )
        return self


class BoolVariableDefinition(BaseModel):
    type: Literal["bool"] = "bool"
    name: str = Field(min_length=1, max_length=50)
    display_name: str = Field(min_length=1, max_length=100)
    description: str | None = None
    default: bool | None = None


VariableDefinition = Annotated[
    IntVariableDefinition | FloatVariableDefinition | StringVariableDefinition | EnumVariableDefinition | BoolVariableDefinition,
    Field(discriminator="type"),
]


class TemplateSnapshot(BaseModel):
    """Captured template state, stored in ``Server.template_snapshot_json``."""

    template_id: int
    template_name: str
    yaml_template: str
    variable_definitions: list[VariableDefinition]
    snapshot_time: str


_variable_list_adapter = TypeAdapter(list[VariableDefinition])


def deserialize_variable_definitions_json(
    variable_definitions_json: str,
) -> list[VariableDefinition]:
    return _variable_list_adapter.validate_json(variable_definitions_json)


def serialize_variable_definitions(
    variable_definitions: list[VariableDefinition],
) -> str:
    return _variable_list_adapter.dump_json(variable_definitions).decode()


class TemplateCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = None
    yaml_template: str = Field(min_length=1)
    variable_definitions: list[VariableDefinition] = Field(default_factory=list)


class TemplateUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = None
    yaml_template: str | None = Field(default=None, min_length=1)
    variable_definitions: list[VariableDefinition] | None = None


class TemplateResponse(BaseModel):
    id: int
    name: str
    description: str | None
    yaml_template: str
    variable_definitions: list[VariableDefinition]
    created_at: datetime
    updated_at: datetime


class TemplateListItem(BaseModel):
    id: int
    name: str
    description: str | None
    variable_count: int
    created_at: datetime


class TemplateSchemaResponse(BaseModel):
    template_id: int
    template_name: str
    json_schema: dict


class AvailablePortsResponse(BaseModel):
    suggested_game_port: int
    suggested_rcon_port: int
    used_ports: list[int]


class TemplatePreviewRequest(BaseModel):
    variable_values: dict


class TemplatePreviewResponse(BaseModel):
    rendered_yaml: str
