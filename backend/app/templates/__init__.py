"""Server template module for template-based server creation."""

from .manager import TemplateManager
from .models import (
    SYSTEM_RESERVED_VARIABLES,
    SYSTEM_VARIABLE_NAMES,
    BoolVariableDefinition,
    EnumVariableDefinition,
    FloatVariableDefinition,
    IntVariableDefinition,
    StringVariableDefinition,
    TemplateCreateRequest,
    TemplateListItem,
    TemplateResponse,
    TemplateSchemaResponse,
    TemplateUpdateRequest,
    VariableDefinition,
    VariableType,
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
    "SYSTEM_RESERVED_VARIABLES",
    "SYSTEM_VARIABLE_NAMES",
    "TemplateCreateRequest",
    "TemplateUpdateRequest",
    "TemplateResponse",
    "TemplateListItem",
    "TemplateSchemaResponse",
]
