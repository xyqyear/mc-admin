"""Pydantic models for template variable definitions."""

from datetime import datetime
from enum import Enum
from typing import Annotated, Literal, Optional, Union

from pydantic import BaseModel, Field, TypeAdapter, model_validator


class VariableType(str, Enum):
    """Variable type enumeration for template variables."""

    INT = "int"
    FLOAT = "float"
    STRING = "string"
    ENUM = "enum"
    BOOL = "bool"


class IntVariableDefinition(BaseModel):
    """Integer variable definition."""

    type: Literal["int"] = "int"
    name: str = Field(min_length=1, max_length=50)
    display_name: str = Field(min_length=1, max_length=100)
    description: Optional[str] = None
    default: Optional[int] = None
    min_value: Optional[int] = None
    max_value: Optional[int] = None


class FloatVariableDefinition(BaseModel):
    """Float variable definition."""

    type: Literal["float"] = "float"
    name: str = Field(min_length=1, max_length=50)
    display_name: str = Field(min_length=1, max_length=100)
    description: Optional[str] = None
    default: Optional[float] = None
    min_value: Optional[float] = None
    max_value: Optional[float] = None


class StringVariableDefinition(BaseModel):
    """String variable definition."""

    type: Literal["string"] = "string"
    name: str = Field(min_length=1, max_length=50)
    display_name: str = Field(min_length=1, max_length=100)
    description: Optional[str] = None
    default: Optional[str] = None
    max_length: Optional[int] = None
    pattern: Optional[str] = None


class EnumVariableDefinition(BaseModel):
    """Enum variable definition."""

    type: Literal["enum"] = "enum"
    name: str = Field(min_length=1, max_length=50)
    display_name: str = Field(min_length=1, max_length=100)
    description: Optional[str] = None
    default: Optional[str] = None
    options: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_default_in_options(self) -> "EnumVariableDefinition":
        """Validate that default value is one of the options."""
        if self.default is not None and self.default not in self.options:
            raise ValueError(
                f"默认值 '{self.default}' 必须是选项列表中的一个: {self.options}"
            )
        return self


class BoolVariableDefinition(BaseModel):
    """Boolean variable definition."""

    type: Literal["bool"] = "bool"
    name: str = Field(min_length=1, max_length=50)
    display_name: str = Field(min_length=1, max_length=100)
    description: Optional[str] = None
    default: Optional[bool] = None


VariableDefinition = Annotated[
    Union[
        IntVariableDefinition,
        FloatVariableDefinition,
        StringVariableDefinition,
        EnumVariableDefinition,
        BoolVariableDefinition,
    ],
    Field(discriminator="type"),
]


class TemplateSnapshot(BaseModel):
    """Snapshot of a template's state, stored in Server.template_snapshot_json."""

    template_id: int
    template_name: str
    yaml_template: str
    variable_definitions: list[VariableDefinition]
    snapshot_time: str


# Shared TypeAdapter for list[VariableDefinition] serialization/deserialization
_variable_list_adapter = TypeAdapter(list[VariableDefinition])


def deserialize_variable_definitions_json(
    variable_definitions_json: str,
) -> list[VariableDefinition]:
    """Parse variable definitions JSON string to list of VariableDefinition."""
    return _variable_list_adapter.validate_json(variable_definitions_json)


def serialize_variable_definitions(
    variable_definitions: list[VariableDefinition],
) -> str:
    """Serialize list of VariableDefinition to JSON string."""
    return _variable_list_adapter.dump_json(variable_definitions).decode()


# Request/Response models for API


class TemplateCreateRequest(BaseModel):
    """Request model for creating a template."""

    name: str = Field(min_length=1, max_length=100)
    description: Optional[str] = None
    yaml_template: str = Field(min_length=1)
    variable_definitions: list[VariableDefinition] = Field(default_factory=list)


class TemplateUpdateRequest(BaseModel):
    """Request model for updating a template."""

    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    description: Optional[str] = None
    yaml_template: Optional[str] = Field(default=None, min_length=1)
    variable_definitions: Optional[list[VariableDefinition]] = None


class TemplateResponse(BaseModel):
    """Response model for template details."""

    id: int
    name: str
    description: Optional[str]
    yaml_template: str
    variable_definitions: list[VariableDefinition]
    created_at: datetime
    updated_at: datetime


class TemplateListItem(BaseModel):
    """Response model for template list item."""

    id: int
    name: str
    description: Optional[str]
    variable_count: int
    created_at: datetime


class TemplateSchemaResponse(BaseModel):
    """Response model for template JSON Schema."""

    template_id: int
    template_name: str
    json_schema: dict


class AvailablePortsResponse(BaseModel):
    """Response model for available ports."""

    suggested_game_port: int
    suggested_rcon_port: int
    used_ports: list[int]


class TemplatePreviewRequest(BaseModel):
    """Request model for previewing rendered YAML."""

    variable_values: dict


class TemplatePreviewResponse(BaseModel):
    """Response model for previewed YAML."""

    rendered_yaml: str
