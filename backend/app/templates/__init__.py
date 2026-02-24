"""Server template module for template-based server creation."""

from .crud import (
    check_name_exists,
    create_template,
    delete_template,
    get_all_templates,
    get_template_by_id,
    get_template_by_name,
    save_template,
)
from .default_variables_crud import get_default_variables, update_default_variables
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
    TemplateSnapshot,
    TemplateUpdateRequest,
    TemplateValidationResult,
    VariableDefinition,
    VariableType,
    deserialize_variable_definitions_json,
    serialize_variable_definitions,
)
from .yaml_utils import are_yaml_semantically_equal

__all__ = [
    # CRUD operations
    "get_all_templates",
    "get_template_by_id",
    "get_template_by_name",
    "check_name_exists",
    "create_template",
    "save_template",
    "delete_template",
    "get_default_variables",
    "update_default_variables",
    # Manager
    "TemplateManager",
    # Models
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
    "TemplateSnapshot",
    "TemplateValidationResult",
    "deserialize_variable_definitions_json",
    "serialize_variable_definitions",
    # Utilities
    "are_yaml_semantically_equal",
]
