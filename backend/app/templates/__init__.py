"""Server template module for template-based server creation."""

from .default_variables import get_default_variables, update_default_variables
from .manager import TemplateManager
from .models import (
    AvailablePortsResponse,
    BoolVariableDefinition,
    EnumVariableDefinition,
    FloatVariableDefinition,
    IntVariableDefinition,
    StringVariableDefinition,
    TemplateCreateRequest,
    TemplateListItem,
    TemplatePreviewRequest,
    TemplatePreviewResponse,
    TemplateResponse,
    TemplateSchemaResponse,
    TemplateUpdateRequest,
    VariableDefinition,
    VariableType,
    cast_variables_json,
    serialize_variables,
)

__all__ = [
    "TemplateManager",
    "VariableType",
    "IntVariableDefinition",
    "FloatVariableDefinition",
    "StringVariableDefinition",
    "EnumVariableDefinition",
    "BoolVariableDefinition",
    "VariableDefinition",
    "TemplateCreateRequest",
    "TemplateUpdateRequest",
    "TemplateResponse",
    "TemplateListItem",
    "TemplateSchemaResponse",
    "AvailablePortsResponse",
    "TemplatePreviewRequest",
    "TemplatePreviewResponse",
    "cast_variables_json",
    "serialize_variables",
    "get_default_variables",
    "update_default_variables",
]
