"""Pydantic models for template variable definitions."""

import json
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


def cast_variables_json(variables_json: str) -> list[VariableDefinition]:
    """Parse variables JSON string to list of VariableDefinition."""
    raw_list = json.loads(variables_json)
    adapter = TypeAdapter(list[VariableDefinition])
    return adapter.validate_python(raw_list)


def get_system_reserved_variables() -> list[VariableDefinition]:
    """Get system reserved variables from dynamic config.

    Returns:
        List of VariableDefinition objects for system reserved variables.
    """
    from ..dynamic_config import config

    result: list[VariableDefinition] = []
    for var_config in config.templates.system_variables:
        if var_config.type == "int":
            result.append(
                IntVariableDefinition(
                    type="int",
                    name=var_config.name,
                    display_name=var_config.display_name,
                    description=var_config.description,
                    default=var_config.default,
                    min_value=var_config.min_value,
                    max_value=var_config.max_value,
                )
            )
        elif var_config.type == "float":
            result.append(
                FloatVariableDefinition(
                    type="float",
                    name=var_config.name,
                    display_name=var_config.display_name,
                    description=var_config.description,
                    default=var_config.default,
                    min_value=var_config.min_value,
                    max_value=var_config.max_value,
                )
            )
        elif var_config.type == "string":
            result.append(
                StringVariableDefinition(
                    type="string",
                    name=var_config.name,
                    display_name=var_config.display_name,
                    description=var_config.description,
                    default=var_config.default,
                    max_length=var_config.max_length,
                    pattern=var_config.pattern,
                )
            )
        elif var_config.type == "enum":
            result.append(
                EnumVariableDefinition(
                    type="enum",
                    name=var_config.name,
                    display_name=var_config.display_name,
                    description=var_config.description,
                    default=var_config.default,
                    options=var_config.options,
                )
            )
        elif var_config.type == "bool":
            result.append(
                BoolVariableDefinition(
                    type="bool",
                    name=var_config.name,
                    display_name=var_config.display_name,
                    description=var_config.description,
                    default=var_config.default,
                )
            )
    return result


def get_system_variable_names() -> set[str]:
    """Get set of system reserved variable names.

    Returns:
        Set of variable names that are reserved by the system.
    """
    from ..dynamic_config import config

    return {v.name for v in config.templates.system_variables}


# Request/Response models for API


class TemplateCreateRequest(BaseModel):
    """Request model for creating a template."""

    name: str = Field(min_length=1, max_length=100)
    description: Optional[str] = None
    yaml_template: str = Field(min_length=1)
    variables: list[VariableDefinition] = Field(default_factory=list)
    copy_from_template_id: Optional[int] = None


class TemplateUpdateRequest(BaseModel):
    """Request model for updating a template."""

    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    description: Optional[str] = None
    yaml_template: Optional[str] = Field(default=None, min_length=1)
    variables: Optional[list[VariableDefinition]] = None


class TemplateResponse(BaseModel):
    """Response model for template details."""

    id: int
    name: str
    description: Optional[str]
    yaml_template: str
    variables: list[VariableDefinition]
    system_variables: list[VariableDefinition]
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
