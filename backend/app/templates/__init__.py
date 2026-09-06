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
    VariableDefinition,
    VariableType,
    deserialize_variable_definitions_json,
    serialize_variable_definitions,
)
from .yaml_utils import are_yaml_semantically_equal

__all__ = [
    "AvailablePortsResponse",
    "BoolVariableDefinition",
    "EnumVariableDefinition",
    "FloatVariableDefinition",
    "IntVariableDefinition",
    "StringVariableDefinition",
    "TemplateCreateRequest",
    "TemplateListItem",
    # Manager
    "TemplateManager",
    "TemplatePreviewRequest",
    "TemplatePreviewResponse",
    "TemplateResponse",
    "TemplateSchemaResponse",
    "TemplateSnapshot",
    "TemplateUpdateRequest",
    "VariableDefinition",
    # Models
    "VariableType",
    # Utilities
    "are_yaml_semantically_equal",
    "check_name_exists",
    "create_template",
    "delete_template",
    "deserialize_variable_definitions_json",
    # CRUD operations
    "get_all_templates",
    "get_default_variables",
    "get_template_by_id",
    "get_template_by_name",
    "save_template",
    "serialize_variable_definitions",
    "update_default_variables",
]
